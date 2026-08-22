"""Turn the committed raw panels into data/product_doses.json.

Offline and re-runnable: the input is committed, so anyone can regenerate the
output and diff it. A panel that does not parse produces NO row and is named in
the report - absence is never a guessed figure, and never a silent one.

A slot can also be dropped WITHIN a panel that otherwise parses fine, when two
published figures for the same (group, method) disagreed in unit - see
src.dose_parse.conflicting_slots. That is not the same defect as an unparsed
panel (the product still gets rows for its other slots) but it is just as
silent if nothing reports it, so main() prints those separately by product
name rather than folding them into `unparsed`.

    python -m scripts.build_product_doses
"""
from __future__ import annotations

import json
from datetime import date

from src.config import DATA_DIR
from src.dose_parse import conflicting_slots, parse_panel

RAW = DATA_DIR / "raw" / "product_panels.json"
OUT = DATA_DIR / "product_doses.json"


def build(panels: dict[str, str]) -> tuple[dict, list[str]]:
    """(table, unparsed names). Pure - no file access, so it is testable."""
    table: dict = {}
    unparsed: list[str] = []
    for name, text in panels.items():
        parsed = parse_panel(text or "")
        if not parsed:
            unparsed.append(name)
            continue
        table[name] = {
            group: {method: {"low": low, "high": high, "unit": unit}
                    for method, (low, high, unit) in methods.items()}
            for group, methods in parsed.items()
        }
    return table, unparsed


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    table, unparsed = build(raw["panels"])

    conflicts = {}
    for name, text in raw["panels"].items():
        slots = conflicting_slots(text or "")
        if slots:
            conflicts[name] = slots

    OUT.write_text(json.dumps(
        {"meta": {"generated": date.today().isoformat(),
                  "source": raw["meta"],
                  "products_with_a_dose": len(table),
                  "products_read": len(raw["panels"])},
         "products": table},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[doses] {len(table)} of {len(raw['panels'])} products carry a per-area dose")
    print(f"[doses] wrote {OUT}")
    if unparsed:
        print(f"[doses] NO PER-AREA DOSE for {len(unparsed)} products:")
        for name in unparsed:
            print(f"          {name}")
    if conflicts:
        print(f"[doses] UNIT CONFLICTS dropped {len(conflicts)} slot(s), reported here rather than silently:")
        for name, slots in conflicts.items():
            for group, method in slots:
                print(f"          {name}: ({group!r}, {method!r})")


if __name__ == "__main__":
    main()
