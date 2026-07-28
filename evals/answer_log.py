"""Per-sample answer log for the eval harness.

The eval scores each generated answer into booleans and would otherwise discard
the text. That has already cost a diagnosis: two NOPRODUCT-backstop leakers
(`pollination_squash`, `local_hachiya_persimmon`) closed as "cause unresolved"
because no answer text survived the run. This module persists every sample as
one JSON line.

DELIBERATELY a pure side effect: nothing here feeds a verdict, a rate, or an exit
code, and a write failure NEVER fails the run - a 25-minute eval must not die of
a disk error. See docs/superpowers/specs/2026-07-28-eval-answer-log-design.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# Module-level so tests can redirect it; read in __init__.
RUNS_DIR: Path = Path(__file__).resolve().parent / "runs"


class AnswerLog:
    """Append one JSON line per generated sample.

    The file is created lazily on the first record(), so a run that generates
    nothing (--fast never calls answer()) leaves no empty file behind.
    """

    def __init__(self, mode: str, provider: str) -> None:
        self._mode = mode
        self._provider = provider
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # The provider stamp carries '/' in hosted model ids, so it goes in the
        # ROWS, never the filename.
        self._path = RUNS_DIR / f"{stamp}-{mode}.jsonl"
        self._count = 0
        self._warned = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def count(self) -> int:
        return self._count

    def record(self, *, case: dict, repeat_index: int, ablated: bool,
               result, grounding: bool, guardrail: bool,
               products_ok: bool | None, no_answer: str | None) -> None:
        """Log one sample. `ablated` is passed in, never inferred from `mode`:
        both modes can produce either value.

        Row construction happens inside the guard too (not just the write):
        a malformed `result` - missing `.answer`, `recommended_products` is
        `None`, an item lacking `.title` - must warn like any other logging
        failure, never raise out of here."""
        self._write(case=case, repeat_index=repeat_index, ablated=ablated,
                    result=result, grounding=grounding, guardrail=guardrail,
                    products_ok=products_ok, no_answer=no_answer)

    def _write(self, *, case: dict, repeat_index: int, ablated: bool,
               result, grounding: bool, guardrail: bool,
               products_ok: bool | None, no_answer: str | None) -> None:
        """All I/O - and the row construction that feeds it - funnels here so
        one guard covers both. Appended and flushed per row: run_faithfulness()
        aborts mid-run, and the aborting sample is precisely the evidence
        someone will want."""
        try:
            row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mode": self._mode,
                "provider": self._provider,
                "case_id": case.get("id"),
                "category": case.get("category"),
                "query": case.get("query"),
                "repeat_index": repeat_index,
                "ablated": ablated,
                "answer": result.answer,
                "products": [p.title for p in result.recommended_products],
                "grounding": grounding,
                "guardrail": guardrail,
                "products_ok": products_ok,
                "no_answer": no_answer,
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._count += 1
        except Exception as exc:  # noqa: BLE001 - logging must never fail a run
            if not self._warned:
                self._warned = True
                print(f"[answers] WARNING: could not write {self._path}: {exc}")
