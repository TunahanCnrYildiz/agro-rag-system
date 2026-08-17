"""Budget inputs, arithmetic, and the framing that keeps a figure an estimate.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from values the user typed
into a form. The route does not call the LLM at all.

NOTHING IS READ OUT OF THE QUESTION. The previous attempt inferred which number
in a sentence belonged to which slot; its review found five wrong money figures.
That inference is gone: values arrive from labelled fields.

THE UNIT IS A SELECTION, NOT AN INFERENCE. A form alone does not fix this. A
farmer who harvested 2 tons from 5 donum holds "2 ton" in mind, not "400 kg/da",
and would type 2000 into a per-dekar field - five times too high, and silent.
So the form asks for the TOTAL harvest with a kg/ton selector and derives the
per-dekar figure itself. Area and price get the same treatment.

This module imports nothing from src/engine.py: with no text parsing there is
nothing to normalise, so it is values in, text out.
"""
from __future__ import annotations

import re

# A complete Turkish number token, with BOTH boundaries anchored. The pattern is
# inherited from the reviewed extraction module: it refuses "1.5" and "1.2.3"
# outright rather than re-parsing them from the middle, which is how a scanning
# regex turns "250.000" into "000".
_NUM_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)$")


def parse_tr_number(text: str) -> float | None:
    """Read one FIELD's contents. Never a sentence - that is the point."""
    token = (text or "").strip()
    if not _NUM_RE.match(token):
        return None
    return float(token.replace(".", "").replace(",", "."))


def format_tr(value: float, decimals: int) -> str:
    """Turkish number formatting: thousands dot, decimal comma.

    Written out rather than delegated to a locale library, which needs the
    locale to be installed on the host and fails differently per platform.
    """
    rounded = round(value, decimals)
    # Derive sign from rounded value, not raw value: values that round to
    # zero display as "0" not "-0", since -0.0 < 0 is False in Python
    sign = "-" if rounded < 0 else ""
    rounded = abs(rounded)
    whole = int(rounded)
    groups = f"{whole:,}".replace(",", ".")
    if decimals <= 0:
        return f"{sign}{groups}"
    frac = round((rounded - whole) * (10 ** decimals))
    return f"{sign}{groups},{frac:0{decimals}d}"
