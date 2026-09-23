"""Download the two FAOSTAT bulk archives this project converts.

TÜİK's inputs are committed under `data/raw/` because they are hand-driven
MEDAS exports that nobody can reproduce from a URL — a converter whose input is
missing can neither be re-run nor inspected. FAOSTAT's inputs are a fixed public
URL, so they stay out of git and this script fetches them instead. What keeps
the conversion auditable is the provenance recorded beside each archive and
copied into `data/world_norms.json`'s meta block: the URL, the server's
Last-Modified, and the byte count.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from scripts._console import use_utf8_console
from src.config import DATA_DIR

_BASE = "https://bulks-faostat.fao.org/production/"
TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class Dataset:
    key: str
    url: str
    member: str


DATASETS: dict[str, Dataset] = {
    "production": Dataset(
        key="Production_Crops_Livestock_E_All_Data_(Normalized)",
        url=_BASE + "Production_Crops_Livestock_E_All_Data_(Normalized).zip",
        member="Production_Crops_Livestock_E_All_Data_(Normalized).csv",
    ),
    "prices": Dataset(
        key="Prices_E_All_Data_(Normalized)",
        url=_BASE + "Prices_E_All_Data_(Normalized).zip",
        member="Prices_E_All_Data_(Normalized).csv",
    ),
}

CACHE_DIR = DATA_DIR / "faostat_cache"


def _archive_path(dataset: Dataset) -> Path:
    return CACHE_DIR / f"{dataset.key}.zip"


def _sidecar_path(dataset: Dataset) -> Path:
    return CACHE_DIR / f"{dataset.key}.provenance.json"


def fetch(key: str, *, force: bool = False, opener=urllib.request.urlopen) -> Path:
    """Return the cached archive for `key`, downloading it when needed."""
    dataset = DATASETS[key]
    archive = _archive_path(dataset)
    if archive.exists() and not force:
        return archive

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with opener(dataset.url, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read()
        last_modified = response.headers.get("Last-Modified", "")

    # Write to a temporary name and validate before adopting it, so an
    # interrupted download never leaves a half archive that later runs
    # would treat as cached.
    staged = archive.with_suffix(".zip.part")
    staged.write_bytes(payload)
    try:
        with zipfile.ZipFile(staged) as archive_file:
            if dataset.member not in archive_file.namelist():
                raise zipfile.BadZipFile(
                    f"{dataset.key}: expected member {dataset.member!r}"
                )
    except zipfile.BadZipFile:
        staged.unlink(missing_ok=True)
        raise

    staged.replace(archive)
    _sidecar_path(dataset).write_text(
        json.dumps(
            {
                "dataset": dataset.key,
                "url": dataset.url,
                "last_modified": last_modified,
                "bytes": len(payload),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return archive


def describe(key: str) -> dict:
    """Return the provenance recorded when `key` was last downloaded."""
    sidecar = _sidecar_path(DATASETS[key])
    if not sidecar.exists():
        raise FileNotFoundError(f"{key} has not been fetched; run this script first")
    return json.loads(sidecar.read_text(encoding="utf-8"))


def main() -> None:
    use_utf8_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()

    for key in DATASETS:
        path = fetch(key, force=args.force)
        meta = describe(key)
        print(f"{key}: {path} ({meta['bytes'] / 1e6:.1f} MB, {meta['last_modified']})")


if __name__ == "__main__":
    main()
