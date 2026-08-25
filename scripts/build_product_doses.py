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
from src.dose_parse import ALL_GROUPS, GROUP_KEYS, conflicting_slots, parse_panel

RAW = DATA_DIR / "raw" / "product_panels.json"
OUT = DATA_DIR / "product_doses.json"
REVIEW = DATA_DIR / "dose_group_scope.json"


def build(panels: dict[str, str], scope: dict[str, list[str]]
          ) -> tuple[dict, list[str], dict, dict]:
    """(table, unparsed names, dropped slots by product, resolved scope). Pure -
    no file access, so it is testable.

    The dropped slots come back from here rather than being re-derived by the
    caller: main() used to walk all 48 panels a second time to collect them,
    which meant the report and the table were built from two separate parses
    and could in principle disagree about the same panel.

    `scope` is the REVIEWED answer to a question no regex can settle: a `hepsi`
    row only tells us the parser saw no group heading, which is true both when
    the page names no crop and when it names crops we do not map to groups.
    An unreviewed `hepsi` row RAISES rather than shipping, because the shipped
    behaviour of an unscoped row would be "answers every group" - a guess, in
    the one place this project has decided never to guess.
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
        rows = {
            group: {method: {"low": low, "high": high, "unit": unit}
                    for method, (low, high, unit) in methods.items()}
            for group, methods in parsed.items()
        }
        # The spec asks the converter to fail LOUDLY on a reversed range rather
        # than write one. The parser refuses them upstream, so this can only
        # fire if that refusal is ever loosened - which is exactly when a
        # silent reversed row would go out with everything else looking fine.
        for group, methods in rows.items():
            for method, dose in methods.items():
                if dose["low"] > dose["high"]:
                    raise ValueError(
                        f"{name} / {group} / {method}: low {dose['low']} is "
                        f"above high {dose['high']} - the parser paired two "
                        f"numbers that do not belong together")
        table[name] = rows
    unreviewed = sorted(n for n, rows in table.items()
                        if ALL_GROUPS in rows and n not in scope)
    if unreviewed:
        raise ValueError(
            f"no reviewed group scope for {unreviewed} - their panels parsed to "
            f"an unqualified '{ALL_GROUPS}' row. Read each panel in "
            f"data/raw/product_panels.json and add an entry to "
            f"data/dose_group_scope.json saying which groups it may answer")
    stale = sorted(n for n in scope
                   if n not in table or ALL_GROUPS not in table[n])
    if stale:
        raise ValueError(
            f"data/dose_group_scope.json reviews {stale}, which ship no "
            f"'{ALL_GROUPS}' row - a review of nothing, sitting in the file "
            f"looking like coverage")
    for name, groups in scope.items():
        unknown = sorted(g for g in groups if g not in GROUP_KEYS)
        if unknown:
            raise ValueError(f"{name}: reviewed for {unknown}, which is not a "
                             f"group we publish (known: {list(GROUP_KEYS)})")
    return table, unparsed, dropped, {n: list(g) for n, g in scope.items()}


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    scope = {name: entry["groups"] for name, entry in review["scope"].items()}
    table, unparsed, conflicts, resolved = build(raw["panels"], scope)

    OUT.write_text(json.dumps(
        # Both findings travel WITH the file, not only to the console. Task 2
        # set that rule for the raw panels - "an empty panel is a finding, and
        # it must travel with the file" - and a dose table has the same need:
        # without these two keys there is no committed way to tell "this
        # product publishes no drip figure" from "its drip figure was dropped
        # as unresolvable", and the answer path needs that difference.
        {"meta": {"generated": date.today().isoformat(),
                  "source": raw["meta"],
                  "reviewed_scope": review["meta"],
                  "products_with_a_dose": len(table),
                  "products_read": len(raw["panels"]),
                  "unparsed": unparsed,
                  "dropped_slots": conflicts},
         "products": table,
         "all_groups_scope": resolved},
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
    if resolved:
        print(f"[doses] {len(resolved)} unqualified row(s) answer only their reviewed groups:")
        for name, groups in resolved.items():
            print(f"          {name}: {', '.join(groups)}")


if __name__ == "__main__":
    main()
