"""Does each answer come back in the language it was asked in?

    python -m evals.run_multilang

Needs the chat model. Asks every question in evals/multilang_set.py through
engine.answer and names the answer's language with src/language.py - the same
detector the server uses, tested on known text in tests/test_language.py. An
answer it cannot name counts as a miss, not a pass.

Measured 2026-10-29 on the local gemma-4-12b: 46/48 before the 12-language
detector and the rewritten refusal (an Uzbek answer in Azerbaijani, an English
refusal in Turkish - both reproduced 4-5 times in 6), 48/48 after.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from evals.multilang_set import KINDS, QUESTIONS  # noqa: E402
from src import engine  # noqa: E402
from src.language import detect_language  # noqa: E402


def main() -> int:
    misses = []
    total = 0
    for language, questions in QUESTIONS.items():
        cells = []
        for kind, question in zip(KINDS, questions):
            got = detect_language(engine.answer(question, []).answer)
            total += 1
            ok = got == language
            cells.append(f"{'ok' if ok else 'MISS'}:{kind}")
            if not ok:
                misses.append((language, kind, got))
        print(f"  {language:12} {'  '.join(cells)}")
    print(f"\n=== {total - len(misses)}/{total} answers in the asker's language ===")
    for language, kind, got in misses:
        print(f"  {language} {kind}: answered in {got}")
    return 0 if not misses else 1


if __name__ == "__main__":
    sys.exit(main())
