"""Download Turkish agriculture papers from DergiPark into docs/books/.

DergiPark (dergipark.org.tr) is Turkey's open-access academic journal platform.
Its ``/search`` endpoint is disallowed by robots.txt, so instead we harvest via
the sanctioned **OAI-PMH** interface (allowed): discover agriculture journals
from ListSets, list their article records, then follow each article's public
landing page to its ``/download/article-file/`` PDF. This adds Turkey-sourced,
peer-reviewed agronomy/soil/plant-nutrition content alongside the (mostly
English) Internet Archive corpus from ``fetch_books.py``.

    python -m src.fetch_dergipark --list-sets          # show matched journals
    python -m src.fetch_dergipark --dry-run --max 40   # preview, download nothing
    python -m src.fetch_dergipark --max 120            # harvest PDFs
    python -m src.fetch_dergipark --set akdenizfderg   # limit to one journal
"""

from __future__ import annotations

import argparse
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

try:
    from .config import BOOKS_DIR
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR  # type: ignore

BASE = "https://dergipark.org.tr"
OAI_URL = f"{BASE}/api/public/oai/"
USER_AGENT = "AgroBotanyBot/0.1 (+https://ekolojiktarim.com.tr/)"

OAI_DELAY = 0.5   # polite delay between OAI API calls
PDF_DELAY = 2.0   # polite delay between PDF downloads (DergiPark rate-limits)
PDF_RETRIES = 4   # attempts when the download endpoint returns HTTP 429
MIN_BYTES = 60_000  # skip tiny stubs / cover-only fragments
# A full ListRecords page is generated on demand and can take ~30s server-side,
# so use a generous timeout and retry a few times before giving up.
OAI_TIMEOUT = 90
OAI_RETRIES = 3

# OAI-PMH XML namespaces.
_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# Verified DergiPark agriculture journal setSpecs (Turkish agriculture faculty
# and national agronomy journals). DergiPark's OAI ListSets only exposes ~100
# journals with no pagination, so relying on it alone misses most; this curated
# list is the primary source, with ListSets discovery merged in as a bonus.
CURATED_JOURNALS = [
    "akdenizfderg",   # Akdeniz Ü. Ziraat Fakültesi Dergisi
    "ankutbd",        # Ankara Ü. - Journal of Agricultural Sciences
    "anadolu",        # Ege Tarımsal Araştırma Enstitüsü Dergisi
    "alinterizbd",    # Alınteri Journal of Agriculture Science
    "tutad",          # Türkiye Tarımsal Araştırmalar Dergisi
    "turkjans",       # Turkish Journal of Agricultural and Natural Sciences
    "ataunizfd",      # Atatürk Ü. - Research in Agricultural Sciences
    "omuanajas",      # OMÜ - Anadolu Tarım Bilimleri Dergisi
    "yyutbd",         # Yüzüncü Yıl Ü. Journal of Agricultural Sciences
    "ksutarimdoga",   # KSÜ Tarım ve Doğa Dergisi
    "harranziraat",   # Harran Tarım ve Gıda Bilimleri Dergisi
    "derim",          # Horticultural Studies
    "gopzfd",         # Gaziosmanpaşa Ü. Ziraat Fakültesi Dergisi
    "ejar",           # Eurasian Journal of Agricultural Research
    "tabad",          # Research Journal of Agricultural Sciences
    "mediterranean",  # Mediterranean Agricultural Sciences
]

# A journal is kept when its name matches one of these (plant/soil-side
# agriculture faculties and agronomy journals).
_AGRI_SET_TERMS = re.compile(
    r"ziraat|tar[ıi]m|agric|agronom|bah[çc]e|bitki|toprak|horticultur|"
    r"field crop|plant|soil",
    re.IGNORECASE,
)
# Within those journals, drop records clearly outside our plant-nutrition /
# soil / botany scope (animal science, fisheries, pure economics, food eng.).
_OFFTOPIC_REC = re.compile(
    r"hayvan|veteriner|zootekni|bal[ıi]k|su [üu]r[üu]nleri|fisher|aquacult|"
    r"ekonomi|pazarlama|market|dairy|poultry|meat|"
    r"\bkoyun|\bsheep|\bkuzu|\blamb|\bke[çc]i|\bgoat|\bs[ıi][ğg][ıi]r|\bcattle|"
    r"\binek|\bbuza[ğg][ıi]|\bivesi|\bawassi|\bbroyler|\bbroiler|\bkanatl[ıi]|"
    r"\brasyon|\bbesi\b|\bkarkas|\bcarcass|\bar[ıi]c[ıi]l[ıi]k|\bipekb[öo]ce[ğg]i",
    re.IGNORECASE,
)

# High-precision livestock/aquaculture filter for cleaning ALREADY-DOWNLOADED
# PDFs. Unlike _OFFTOPIC_REC (applied to short, clean OAI title+subject), this
# runs against noisy full-page text, so it must avoid terms that collide with
# plant-science vocabulary: NOT `ekonomi` (Tarım Ekonomisi dept), `market`,
# `hayvan` (Hayvancılık MYO name), `bal[ıi]k` (surname Balık), nor bare
# `goat`/`dairy`/`cattle` (goat/cattle manure are on-topic organic fertilizers).
# `rasyon`/`koyun` are whole-word anchored so they don't match
# `konsantrasyon`/`Koyuncu`; cattle is reached only via `süt/besi sığır`.
_OFFTOPIC_CLEANUP_REC = re.compile(
    r"zootekni|veteriner|\bivesi\b|\bawassi\b|\bbroyler\b|\bbroiler\b|"
    r"\bkarkas|\brasyon\b|\bbuza[ğg][ıi]|\bkuzu\b|\blamb\b|\bsheep\b|"
    r"\bkoyun\b|\bkanatl[ıi]|su [üu]r[üu]nleri|aquacult|fisher|"
    r"s[üu]t s[ıi][ğg][ıi]r|besi s[ıi][ğg][ıi]r",
    re.IGNORECASE,
)

_ARTICLE_URL = re.compile(r"/pub/[^/]+/article/(\d+)")
_DOWNLOAD_LINK = re.compile(r"/[a-z]{2}/download/article-file/\d+")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "tr,en"})
    return s


def _oai(session: requests.Session, params: dict) -> ET.Element | None:
    """Call the OAI-PMH endpoint and return the parsed root element, retrying a
    few times with backoff since a full page can be slow to generate."""
    for attempt in range(1, OAI_RETRIES + 1):
        try:
            resp = session.get(OAI_URL, params=params, timeout=OAI_TIMEOUT)
            resp.raise_for_status()
            return ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as exc:
            if attempt == OAI_RETRIES:
                print(f"[dergipark] OAI failed after {OAI_RETRIES} tries ({params}): {exc}")
                return None
            time.sleep(2 * attempt)
    return None


# --------------------------------------------------------------------------- #
# Journal (set) discovery
# --------------------------------------------------------------------------- #
def discover_sets(session: requests.Session, max_pages: int) -> list[tuple[str, str]]:
    """Page through ListSets and return (setSpec, name) for agriculture journals."""
    out: list[tuple[str, str]] = []
    params = {"verb": "ListSets"}
    for _ in range(max_pages):
        root = _oai(session, params)
        if root is None:
            break
        for s in root.findall(".//oai:set", _NS):
            spec = (s.findtext("oai:setSpec", default="", namespaces=_NS) or "").strip()
            name = (s.findtext("oai:setName", default="", namespaces=_NS) or "").strip()
            if spec and _AGRI_SET_TERMS.search(name):
                out.append((spec, name))
        token = root.findtext(".//oai:resumptionToken", default="", namespaces=_NS)
        if not token:
            break
        params = {"verb": "ListSets", "resumptionToken": token}
        time.sleep(OAI_DELAY)
    # Dedupe, keep order.
    seen: set[str] = set()
    uniq = [(s, n) for s, n in out if not (s in seen or seen.add(s))]
    return uniq


# --------------------------------------------------------------------------- #
# Record (article) listing
# --------------------------------------------------------------------------- #
def _article_from_record(rec: ET.Element) -> tuple[str, str] | None:
    """Return (article_id, landing_url) for a record, filtering off-topic ones."""
    ids = [e.text or "" for e in rec.findall(".//dc:identifier", _NS)]
    landing = next((u for u in ids if _ARTICLE_URL.search(u)), "")
    m = _ARTICLE_URL.search(landing)
    if not m:
        return None
    blob = " ".join(
        (e.text or "")
        for tag in ("dc:title", "dc:subject")
        for e in rec.findall(f".//{tag}", _NS)
    )
    if _OFFTOPIC_REC.search(blob):
        return None
    return m.group(1), landing


def list_articles(
    session: requests.Session, set_spec: str, max_per_set: int
) -> list[tuple[str, str]]:
    """List (article_id, landing_url) for one journal, following resumption."""
    out: list[tuple[str, str]] = []
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": set_spec}
    while len(out) < max_per_set:
        root = _oai(session, params)
        if root is None:
            break
        for rec in root.findall(".//oai:record", _NS):
            got = _article_from_record(rec)
            if got:
                out.append(got)
        token = root.findtext(".//oai:resumptionToken", default="", namespaces=_NS)
        if not token:
            break
        params = {"verb": "ListRecords", "resumptionToken": token}
        time.sleep(OAI_DELAY)
    return out[:max_per_set]


# --------------------------------------------------------------------------- #
# PDF download
# --------------------------------------------------------------------------- #
def _pdf_link(session: requests.Session, landing_url: str) -> str | None:
    """Fetch an article landing page and return its PDF download URL, or None."""
    try:
        resp = session.get(landing_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[dergipark]   ! landing fetch failed: {exc}")
        return None
    m = _DOWNLOAD_LINK.search(resp.text)
    return f"{BASE}{m.group(0)}" if m else None


def download(session: requests.Session, url: str, dest: Path) -> bool:
    """Stream a PDF to disk; validate %PDF header + size. Returns True on success.

    DergiPark rate-limits the download endpoint, so a 429 is retried after the
    server's Retry-After (or a growing backoff) rather than skipped outright.
    """
    resp = None
    for attempt in range(1, PDF_RETRIES + 1):
        try:
            resp = session.get(url, stream=True, timeout=120)
        except requests.RequestException as exc:
            print(f"[dergipark]   ! download error: {exc}")
            return False
        if resp.status_code != 429:
            break
        wait = int(resp.headers.get("Retry-After", "0") or 0) or min(30, 5 * attempt)
        resp.close()
        if attempt < PDF_RETRIES:
            print(f"[dergipark]   . rate-limited (429), waiting {wait}s")
            time.sleep(wait)
    if resp is None or resp.status_code != 200:
        code = resp.status_code if resp is not None else "?"
        print(f"[dergipark]   ! http {code}, skipping")
        return False

    tmp = dest.with_suffix(".part")
    written = 0
    first = b""
    try:
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                if not first:
                    first = chunk[:4]
                    if first != b"%PDF":
                        print("[dergipark]   ! not a real PDF, skipping")
                        break
                fh.write(chunk)
                written += len(chunk)
    finally:
        resp.close()

    if first == b"%PDF" and written >= MIN_BYTES:
        tmp.replace(dest)
        print(f"[dergipark]   + saved {dest.name} ({written // 1024} KB)")
        return True
    tmp.unlink(missing_ok=True)
    if first == b"%PDF":
        print(f"[dergipark]   ! too small ({written // 1024} KB), skipping")
    return False


def _first_page_text(path: Path) -> str:
    """Extract first-page text for local off-topic classification."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001
        return ""
    if not reader.pages:
        return ""
    try:
        return reader.pages[0].extract_text() or ""
    except Exception:  # noqa: BLE001
        return ""


def is_offtopic_text(text: str) -> bool:
    """True when first-page text matches the high-precision livestock/aquaculture
    cleanup filter (distinct from the fetcher's broad topical _OFFTOPIC_REC)."""
    return bool(_OFFTOPIC_CLEANUP_REC.search(text))


def _offtopic_candidates(text_fn=_first_page_text) -> list[tuple[Path, list[str]]]:
    """Return (path, matched_terms) for dp_*.pdf whose first page matches the
    cleanup filter, so a human can review why each was flagged."""
    parts = [(t, re.compile(t, re.IGNORECASE))
             for t in _OFFTOPIC_CLEANUP_REC.pattern.split("|")]
    out: list[tuple[Path, list[str]]] = []
    for p in sorted(BOOKS_DIR.glob("dp_*.pdf")):
        txt = text_fn(p)
        if _OFFTOPIC_CLEANUP_REC.search(txt):
            out.append((p, [t for t, c in parts if c.search(txt)]))
    return out


def clean_offtopic(store=None, apply: bool = False,
                   text_fn=_first_page_text) -> int:
    """Report (default) or apply removal of already-downloaded off-topic papers.

    Report-only: scan dp_*.pdf, write flagged filenames + matched terms to a
    ``offtopic_candidates.txt`` report beside docs/books/ and print them; move
    and delete nothing. With ``apply=True`` each candidate is moved to
    ``docs/books/_offtopic/`` and its chunks are deleted from the store. Local
    only; no network. Returns the number of candidates."""
    candidates = _offtopic_candidates(text_fn)
    report = BOOKS_DIR.parent / "offtopic_candidates.txt"
    lines = [f"{p.name}\t{','.join(terms)}" for p, terms in candidates]
    report.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"[clean] {len(candidates)} off-topic candidate(s); report: {report}")
    for line in lines:
        print(f"[clean]   {line}")
    if not apply:
        print("[clean] report-only. Review the report, then re-run with --apply "
              "to move these files and delete their chunks.")
        return len(candidates)
    if not candidates:
        return 0
    if store is None:
        from .ingest import get_vector_store
        store = get_vector_store()
    offtopic_dir = BOOKS_DIR / "_offtopic"
    offtopic_dir.mkdir(exist_ok=True)
    for p, _terms in candidates:
        got = store.get(where={"source": p.name})
        if got.get("ids"):
            store.delete(ids=got["ids"])
        p.replace(offtopic_dir / p.name)
        print(f"[clean]   moved {p.name} ({len(got.get('ids', []))} chunks removed)")
    return len(candidates)


# --------------------------------------------------------------------------- #
# Drivers
# --------------------------------------------------------------------------- #
def _resolve_journals(session: requests.Session, set_pages: int) -> list[str]:
    """Curated agriculture journals, plus any extra matches ListSets surfaces."""
    discovered = [spec for spec, _ in discover_sets(session, set_pages)]
    specs = list(dict.fromkeys(CURATED_JOURNALS + discovered))
    print(f"[dergipark] targeting {len(specs)} journal(s) "
          f"({len(CURATED_JOURNALS)} curated + {len(discovered)} discovered)")
    return specs


def _collect_candidates(
    session: requests.Session, specs: list[str], per_journal: int
) -> list[tuple[str, str]]:
    """Gather (article_id, landing_url) across journals, deduped by id."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for spec in specs:
        arts = list_articles(session, spec, per_journal)
        kept = 0
        for aid, url in arts:
            if aid in seen:
                continue
            seen.add(aid)
            out.append((aid, url))
            kept += 1
        print(f"[dergipark] journal '{spec}': {kept} articles")
        time.sleep(OAI_DELAY)
    return out


def run(
    set_spec: str | None, max_books: int, per_journal: int,
    set_pages: int, dry_run: bool,
) -> int:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    session = _session()

    specs = [set_spec] if set_spec else _resolve_journals(session, set_pages)
    candidates = _collect_candidates(session, specs, per_journal)
    print(f"[dergipark] {len(candidates)} candidate articles; target {max_books}\n")

    if dry_run:
        for i, (aid, url) in enumerate(candidates[:max_books], 1):
            print(f"{i:>3}  {aid:>8}  {url}")
        print(f"\n[dergipark] preview only ({min(len(candidates), max_books)} shown). "
              "Re-run without --dry-run to download.")
        return 0

    saved = 0
    for aid, url in candidates:
        if saved >= max_books:
            break
        dest = BOOKS_DIR / f"dp_{aid}.pdf"
        if dest.exists():
            print(f"[dergipark]   = already have {dest.name}, skipping")
            continue
        pdf = _pdf_link(session, url)
        if not pdf:
            continue
        print(f"[dergipark] article {aid}")
        if download(session, pdf, dest):
            saved += 1
        time.sleep(PDF_DELAY)

    print(f"\n[dergipark] DONE. downloaded {saved} paper(s) into {BOOKS_DIR}")
    if saved:
        print("[dergipark] next: python -m src.ingest")
    return saved


def main() -> None:
    p = argparse.ArgumentParser(
        description="Harvest Turkish agriculture papers from DergiPark (OAI-PMH)."
    )
    p.add_argument("--max", type=int, default=80, help="Max PDFs to download.")
    p.add_argument("--per-journal", type=int, default=25,
                   help="Max articles pulled per journal.")
    p.add_argument("--set", default=None,
                   help="Limit to one journal setSpec (e.g. akdenizfderg).")
    p.add_argument("--set-pages", type=int, default=60,
                   help="Max ListSets pages to scan during discovery.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview candidate articles without downloading.")
    p.add_argument("--list-sets", action="store_true",
                   help="List matched agriculture journals and exit.")
    p.add_argument("--clean-offtopic", action="store_true",
                   help="Scan already-downloaded PDFs and report off-topic "
                        "(livestock/aquaculture) candidates. Report-only unless "
                        "--apply is given.")
    p.add_argument("--apply", action="store_true",
                   help="With --clean-offtopic, actually move flagged PDFs to "
                        "docs/books/_offtopic/ and delete their store chunks.")
    args = p.parse_args()

    if args.clean_offtopic:
        clean_offtopic(apply=args.apply)
        return

    if args.list_sets:
        session = _session()
        for spec in _resolve_journals(session, args.set_pages):
            print(f"  {spec}")
        return

    run(
        set_spec=args.set,
        max_books=args.max,
        per_journal=args.per_journal,
        set_pages=args.set_pages,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
