"""Download a prebuilt vector store and unpack it into data/vector_store/.

Rebuilding the corpus from scratch does NOT reproduce it: the Internet Archive
returns different books over time, so a machine that re-fetches ends up with a
different, usually much smaller, knowledge base than the one the system was
measured against. A fresh machine must therefore RECEIVE the store, not build
one. This module is how.

    python -m src.fetch_vector_store                    # uses VECTOR_STORE_URL
    python -m src.fetch_vector_store --url <URL>
    python -m src.fetch_vector_store --force            # replace an existing store

Source-agnostic on purpose. Any URL that serves the archive works - a GitHub
release asset, an S3/R2 object, a plain web server - so moving the file later is
a config change, not a code change. Google Drive share links are also accepted
and handled specially, because Drive answers a large-file request with a
virus-scan confirmation PAGE rather than the bytes.

Two failure modes are worth knowing about before choosing Drive as the host:
a public Drive file has a daily download quota, and once it is exhausted Google
serves an error page (not an error status) for roughly a day; and the link is
tied to one person's account. Both are why `--url` exists.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

from src.config import VECTOR_STORE_DIR, settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

_CHUNK = 8 << 20          # 8 MiB
_TIMEOUT = 60             # per-read; a 900 MB body legitimately takes minutes
_DRIVE_HOSTS = ("drive.google.com", "drive.usercontent.google.com")

# Exit codes are a CONTRACT with docker-entrypoint.sh, which decides from them
# whether falling back to fetch+ingest is acceptable. Two failures look the same
# from the outside and must not be treated the same:
#
#   1  COULD NOT OBTAIN the archive - no URL, Drive quota, network, a truncated
#      body. The archive is simply unavailable, and building a corpus locally is
#      the designed answer. Falling back is correct.
#
#   2  OBTAINED SOMETHING THAT IS NOT THE CORPUS - checksum mismatch, no
#      chroma.sqlite3 inside, zero embeddings. The download succeeded and what
#      arrived is not what the maintainer published. Falling back here would
#      replace a loud, fixable problem with a silent one: a corpus roughly a
#      tenth the size that answers questions badly rather than failing. That is
#      precisely what the checksum exists to prevent, so we stop instead.
EXIT_UNAVAILABLE = 1
EXIT_INTEGRITY = 2


def _fail_integrity(message: str) -> "NoReturn":  # noqa: F821
    """Stop with exit code 2. See EXIT_INTEGRITY above for why this is not a
    fallback-able failure."""
    print(f"BUTUNLUK HATASI: {message}", file=sys.stderr)
    print("Arsiv indirildi ama beklenen havuz DEGIL. fetch+ingest'e dusmek bunu "
          "gizler ve onda bir buyuklukte bir korpus kurar - onun yerine "
          "duruyoruz.", file=sys.stderr)
    raise SystemExit(EXIT_INTEGRITY)


def _drive_id(url: str) -> str | None:
    """The file id inside a Google Drive share link, or None for a plain URL."""
    if not any(h in url for h in _DRIVE_HOSTS):
        return None
    for pattern in (r"/file/d/([A-Za-z0-9_-]{10,})",   # .../file/d/<id>/view
                    r"[?&]id=([A-Za-z0-9_-]{10,})"):   # ...?id=<id>
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise SystemExit(f"Drive link tanindi ama dosya id'si cikarilamadi: {url}")


def _open_stream(session: requests.Session, url: str):
    """A streaming GET, with Drive's large-file confirmation handled.

    Drive does not fail loudly for a big file: it returns 200 with an HTML
    interstitial. We ask for the confirmed download directly, and if the answer
    still looks like a page rather than a file, we pull the confirm token out of
    it and retry once.
    """
    fid = _drive_id(url)
    if fid is None:
        return session.get(url, stream=True, timeout=_TIMEOUT)

    direct = "https://drive.usercontent.google.com/download"
    params = {"id": fid, "export": "download", "confirm": "t"}
    resp = session.get(direct, params=params, stream=True, timeout=_TIMEOUT)
    if "text/html" not in resp.headers.get("Content-Type", ""):
        return resp

    body = resp.text
    resp.close()
    token = None
    for pattern in (r'name="confirm"\s+value="([^"]+)"', r"confirm=([0-9A-Za-z_-]+)"):
        m = re.search(pattern, body)
        if m:
            token = m.group(1)
            break
    if token is None:
        if "quota" in body.lower():
            raise SystemExit(
                "Google Drive indirme kotasi dolmus - bu link bir sure "
                "(genellikle ~24 saat) dosya yerine hata sayfasi dondurecek. "
                "Dosyayi baska bir kaynaga koyup --url ile verin."
            )
        raise SystemExit(
            "Drive dosya yerine bir HTML sayfasi dondurdu ve onay jetonu "
            "bulunamadi. Link 'baglantiya sahip herkes' olarak paylasildi mi?"
        )
    params["confirm"] = token
    return session.get(direct, params=params, stream=True, timeout=_TIMEOUT)


def _download(url: str, dest: Path) -> None:
    """Stream the archive to `dest`, printing progress."""
    with requests.Session() as session:
        resp = _open_stream(session, url)
        with resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(_CHUNK):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r  {done / 1048576:.0f} / {total / 1048576:.0f} MB"
                              f"  ({done / total:.0%})", end="", flush=True)
                    else:
                        print(f"\r  {done / 1048576:.0f} MB", end="", flush=True)
            print()
    if dest.stat().st_size == 0:
        raise SystemExit("indirilen dosya bos.")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(blk)
    return h.hexdigest()


def _check_archive(path: Path) -> None:
    """Fail loudly on anything that is not a real zip.

    This is the guard that catches a served error page - Drive's quota notice
    arrives with status 200, so without this we would write HTML into a file
    named .zip and only discover it much later.
    """
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic[:2] != b"PK":
        head = path.read_bytes()[:200].decode("utf-8", "replace")
        raise SystemExit(
            "indirilen dosya bir zip degil - buyuk ihtimalle bir hata sayfasi.\n"
            f"ilk baytlar: {head!r}"
        )
    if not zipfile.is_zipfile(path):
        raise SystemExit("dosya bozuk: zip olarak acilamiyor (yarim inmis olabilir).")


def _report_store(store_dir: Path) -> None:
    """Say what actually landed, from the store's own metadata.

    Cheap on purpose: reads sqlite directly rather than opening the store
    through Chroma, so a bootstrap needs no embedding model to verify itself.
    """
    db = store_dir / "chroma.sqlite3"
    if not db.exists():
        _fail_integrity(f"acilan arsivde chroma.sqlite3 yok: {store_dir}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("select name from collections")]
        n = con.execute("select count(*) from embeddings").fetchone()[0]
    finally:
        con.close()
    print(f"  koleksiyon : {', '.join(names) or '(yok)'}")
    print(f"  parca      : {n:,}")
    if n == 0:
        _fail_integrity("havuz bos gorunuyor - yanlis arsiv olabilir.")


def run(url: str, force: bool = False, expected_sha: str | None = None) -> None:
    store = Path(VECTOR_STORE_DIR)
    populated = store.exists() and any(
        p for p in store.iterdir() if p.name != ".gitkeep"
    )
    if populated and not force:
        print(f"{store} zaten dolu - indirme atlaniyor (--force ile degistirin).")
        return

    tmp_dir = Path(tempfile.mkdtemp(prefix="vstore-"))
    archive = tmp_dir / "vector_store.zip"
    try:
        print(f"indiriliyor: {url}")
        _download(url, archive)
        _check_archive(archive)

        digest = _sha256(archive)
        print(f"  sha256     : {digest}")
        if expected_sha and digest.lower() != expected_sha.lower():
            _fail_integrity(
                "SHA256 UYUSMUYOR - dosya yarim inmis ya da degismis.\n"
                f"  beklenen : {expected_sha}\n"
                f"  gelen    : {digest}"
            )
        if not expected_sha:
            print("  (beklenen sha verilmedi - butunluk dogrulanmadi)")

        unpack = tmp_dir / "unpacked"
        with zipfile.ZipFile(archive) as z:
            z.extractall(unpack)
        _report_store(unpack)

        # Swap only after the new store has been checked, and keep a real old
        # one under a sibling name rather than deleting it: this file is
        # expensive and, once rebuilt elsewhere, unreproducible.
        #
        # The destination must NOT exist before the move. A fresh clone ships
        # data/vector_store/.gitkeep, so the directory is present but empty -
        # and shutil.move onto an existing directory moves the source INSIDE it,
        # which would bury the store one level down and leave the system
        # apparently working with no corpus at all.
        if store.exists():
            if populated:
                backup = store.with_name(store.name + "_replaced")
                if backup.exists():
                    shutil.rmtree(backup)
                store.rename(backup)
                print(f"  onceki havuz {backup} olarak saklandi")
            else:
                shutil.rmtree(store)
        store.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(unpack), str(store))
        print(f"tamam: {store}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # Both default to the configured archive, so a fresh machine needs no
    # arguments and no environment at all. settings already layers .env and the
    # environment over the values in config.py, so VECTOR_STORE_URL /
    # VECTOR_STORE_SHA256 still override without any extra plumbing here.
    p.add_argument("--url", default=settings.vector_store_url,
                   help="archive URL (default: settings.vector_store_url)")
    p.add_argument("--sha256", default=settings.vector_store_sha256,
                   help="expected SHA-256 (default: settings.vector_store_sha256)")
    p.add_argument("--force", action="store_true",
                   help="replace an existing store instead of skipping")
    args = p.parse_args()
    if not args.url:
        raise SystemExit(
            "URL yok. --url verin, VECTOR_STORE_URL ayarlayin, ya da "
            "src/config.py'deki vector_store_url varsayilanini doldurun."
        )
    run(args.url, force=args.force, expected_sha=args.sha256)


if __name__ == "__main__":
    main()
