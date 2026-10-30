"""Convert FAO-56's Tables 11 and 12 into `data/crop_stages.json`.

The season calendar (Hüseyin's PDF p5) is built from PUBLISHED figures only -
decided 2026-10-30: a representative calendar with an engineer warning, every
line from a cited source, none from our own agronomy. FAO Irrigation and
Drainage Paper 56 (Allen et al., 1998) is that source for the stage half:

  Table 11 - days in each development stage (initial, development, mid-season,
             late season), by planting month and climatic region;
  Table 12 - single crop coefficients Kc (initial, mid, end): the crop's water
             use relative to a reference grass, per stage.

Values are kept AS PUBLISHED, as text: "50/30" and "Oct/Jan" are two readings
the table gives and choosing one belongs to whoever assembles a calendar, not
to this conversion. Footnote marks (<SUP>) are dropped - they would otherwise
fuse into the number ("1.05" + footnote 2 reads "1.052").

    curl -o x0490e0b.htm https://www.fao.org/4/x0490e/x0490e0b.htm
    python -m scripts.build_crop_stages --html x0490e0b.htm
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

from scripts._console import use_utf8_console
from src.config import DATA_DIR

SOURCE_URL = "https://www.fao.org/4/x0490e/x0490e0b.htm"
SOURCE_TITLE = ("FAO Irrigation and Drainage Paper No. 56 - Crop evapotranspiration "
                "(Allen, Pereira, Raes, Smith, 1998)")
OUT = DATA_DIR / "crop_stages.json"

# "a. Small Vegetables" ... "p. Special" - the tables' crop-group rows.
_GROUP = re.compile(r"^[a-p]\.\s")
_STAGE_KEYS = ("init", "dev", "mid", "late", "total", "plant", "region")


def _cells(row_html: str) -> list[str]:
    row_html = re.sub(r"<sup>.*?</sup>", "", row_html, flags=re.S | re.I)
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.S | re.I)
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in cells]


def _table(page: str, start: str, stop: str) -> list[list[str]]:
    i = page.find(start)
    if i < 0:
        raise ValueError(f"{start!r} not found - has the page changed?")
    j = page.find(stop, i)
    section = page[i:j if j > 0 else len(page)]
    rows = [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", section, flags=re.S | re.I)]
    return [r for r in rows if any(r)]


def parse_stages(page: str) -> list[dict]:
    """Table 11. A row without a crop name continues the crop above it."""
    out, group, crop = [], None, None
    for cells in _table(page, "TABLE 11", "TABLE 12")[1:]:   # [0] is the header
        if len(cells) == 1 or (cells[0] and _GROUP.match(cells[0])):
            group = cells[0]
            continue
        if len(cells) == 8:
            crop, values = cells[0] or crop, cells[1:]
        elif len(cells) == 7:
            values = cells
        else:
            continue
        out.append({"crop": crop, "group": group, **dict(zip(_STAGE_KEYS, values))})
    return out


def parse_kc(page: str) -> list[dict]:
    """Table 12. A crop row with no Kc ini takes its group's, and says so -
    the table prints the group value once, on the group row."""
    out, group, group_kc, crop = [], None, {}, None
    for cells in _table(page, "TABLE 12", "TABLE 13")[1:]:
        if cells[0] and _GROUP.match(cells[0]):
            group = cells[0]
            group_kc = dict(zip(("kc_ini", "kc_mid", "kc_end"), cells[1:4]))
            continue
        if len(cells) == 6 and not cells[0]:          # "- dry" under "Onions"
            variant, values = cells[1], cells[2:]
        elif len(cells) == 5:
            crop, variant, values = cells[0], None, cells[1:]
        else:
            continue
        kc_ini, kc_mid, kc_end, height = values
        if not any((kc_ini, kc_mid, kc_end)):         # a crop row whose variants follow
            continue
        out.append({
            "crop": crop, "variant": variant, "group": group,
            "kc_ini": kc_ini or group_kc.get("kc_ini", ""),
            "kc_ini_from_group": not kc_ini,
            "kc_mid": kc_mid, "kc_end": kc_end, "height_m": height,
        })
    return out


def build(page: str, retrieved: str) -> dict:
    return {
        "meta": {
            "source": SOURCE_TITLE,
            "url": SOURCE_URL,
            "tables": {"11": "Lengths of crop development stages (days)",
                       "12": "Single (time-averaged) crop coefficients Kc"},
            "retrieved": retrieved,
            "note": ("Values as published, as text. Reuse terms for a commercial "
                     "product have not been confirmed with FAO."),
        },
        "stages": parse_stages(page),
        "kc": parse_kc(page),
    }


def main() -> None:
    use_utf8_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--html", required=True, type=Path,
                        help="the saved FAO-56 chapter 6 page (x0490e0b.htm)")
    args = parser.parse_args()
    page = args.html.read_text(encoding="latin-1")
    data = build(page, date.today().isoformat())
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(data['stages'])} stage rows, {len(data['kc'])} Kc rows -> {OUT}")


if __name__ == "__main__":
    main()
