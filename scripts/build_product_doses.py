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

from scripts._console import use_utf8_console
from src.config import DATA_DIR
from src.dose_parse import ALL_GROUPS, GROUP_KEYS, conflicting_slots, parse_panel

RAW = DATA_DIR / "raw" / "product_panels.json"
OUT = DATA_DIR / "product_doses.json"
REVIEW = DATA_DIR / "dose_group_scope.json"


def build(panels: dict[str, str], scope: dict[str, list[str]],
          shared: dict | None = None
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

    `shared` is the second REVIEWED answer to the same kind of question: a
    page that publishes ONE figure for TWO groups in one sentence. HIGRO
    FERRY writes "Tek yillik tarla ve endustri bitkileri ILE sebzelerde ...
    1-2 litre", and _segments opens a segment on "sebzelerde" only, so field
    growers get nothing for a figure the maker published for them. Widening
    the `tarla` pattern to span intervening words was measured and refused -
    it swallows FERFORCE's "Tarla sebzelerinde", a VEGETABLE sub-case - so
    the coverage is recorded by a person instead, with the sentence quoted.
    Measured 2026-08-26: exactly one of the 48 panels loses a group this way.
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
    for name, entry in (shared or {}).items():
        rows = table.get(name)
        if rows is None:
            raise ValueError(
                f"data/dose_group_scope.json shares a row for {name!r}, which "
                f"ships no dose at all - a review of nothing, sitting in the "
                f"file looking like coverage")
        source = entry["from"]
        if source not in rows:
            raise ValueError(
                f"{name}: reviewed to share its {source!r} row, but it ships no "
                f"{source!r} row - the panel changed under the review")
        # THE GUARD THAT MAKES THE REVIEW MEAN SOMETHING. A person approved this
        # copy on the strength of one published sentence, and recorded which
        # methods that sentence produced. If the page later gives the source
        # group another figure, copying it too would widen a row nobody
        # approved - so the build stops and a human re-reads the panel.
        found, expected = sorted(rows[source]), sorted(entry["expect_methods"])
        if found != expected:
            raise ValueError(
                f"{name}: its {source!r} row now carries {found}, but the review "
                f"in data/dose_group_scope.json recorded expect_methods "
                f"{expected}. Re-read the panel and update the entry rather "
                f"than shipping a copy nobody approved")
        for group in entry["also"]:
            if group not in GROUP_KEYS:
                raise ValueError(
                    f"{name}: shared to {group!r}, which is not a group we "
                    f"publish (known: {list(GROUP_KEYS)})")
            if group in rows:
                raise ValueError(
                    f"{name}: shared to {group!r}, which already ships its own "
                    f"row. If the parser learned to read this page itself, the "
                    f"entry is redundant - delete it rather than overwrite a "
                    f"published row")
            # A fresh dict per method: two groups sharing one mapping means a
            # later edit to either silently edits both.
            rows[group] = {method: dict(dose)
                           for method, dose in rows[source].items()}
    return table, unparsed, dropped, {n: list(g) for n, g in scope.items()}


def main() -> None:
    use_utf8_console()
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    scope = {name: entry["groups"] for name, entry in review["scope"].items()}
    shared = review.get("shared_rows", {})
    table, unparsed, conflicts, resolved = build(raw["panels"], scope, shared)

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
                  "dropped_slots": conflicts,
                  # Which rows were COPIED by review rather than published
                  # under their own heading. Without this a reader diffing the
                  # file cannot tell the two apart.
                  "shared_rows": {name: {"from": e["from"], "also": list(e["also"])}
                                  for name, e in shared.items()},
                  },
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
    if shared:
        print(f"[doses] {len(shared)} reviewed shared row(s):")
        for name, entry in shared.items():
            print(f"          {name}: {entry['from']} -> {', '.join(entry['also'])}")


if __name__ == "__main__":
    main()
