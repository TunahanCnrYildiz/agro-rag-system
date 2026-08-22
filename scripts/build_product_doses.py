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


def build(panels: dict[str, str]) -> tuple[dict, list[str], dict]:
    """(table, unparsed names, dropped slots by product). Pure - no file
    access, so it is testable.

    The dropped slots come back from here rather than being re-derived by the
    caller: main() used to walk all 48 panels a second time to collect them,
    which meant the report and the table were built from two separate parses
    and could in principle disagree about the same panel.
    """
    table: dict = {}
    unparsed: list[str] = []
    dropped: dict[str, list[list[str]]] = {}
    for name, text in panels.items():
        slots = conflicting_slots(text or "")
        if slots:
            dropped[name] = [[group, method] for group, method in slots]
        parsed = parse_panel(text or "")
        if not parsed:
            unparsed.append(name)
            continue
        table[name] = {
            group: {method: {"low": low, "high": high, "unit": unit}
                    for method, (low, high, unit) in methods.items()}
            for group, methods in parsed.items()
        }
    return table, unparsed, dropped


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    table, unparsed, conflicts = build(raw["panels"])

    OUT.write_text(json.dumps(
        # Both findings travel WITH the file, not only to the console. Task 2
        # set that rule for the raw panels - "an empty panel is a finding, and
        # it must travel with the file" - and a dose table has the same need:
        # without these two keys there is no committed way to tell "this
        # product publishes no drip figure" from "its drip figure was dropped
        # as unresolvable", and the answer path needs that difference.
        {"meta": {"generated": date.today().isoformat(),
                  "source": raw["meta"],
                  "products_with_a_dose": len(table),
                  "products_read": len(raw["panels"]),
                  "unparsed": unparsed,
                  "dropped_slots": conflicts},
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
