"""Let these scripts print Turkish names on a console that is not UTF-8.

Windows hands a piped stdout the ANSI code page - cp1252 here - and cp1252 has
no dotted I. So `print(name)` RAISED on the first `HİGRO BARF`, and it raised
inside the reporting block that exists to name loudly every panel the parser
could not read: the feature died exactly when it had something to report, and
the non-zero exit made a build that had already written its output look failed.

stderr does not raise, because Python gives it `backslashreplace`. It is no
better off: `Kg/Meyve Veren A\u011fa?` is a skipped-row report nobody can read.

The env-var workaround (PYTHONIOENCODING=utf-8) fixes both, and asks every
caller to remember it forever. This does not.
"""
from __future__ import annotations

import sys


def use_utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8, best effort.

    Call it first thing in main(), before anything can print a name.

    A stream that cannot be reconfigured is left alone rather than replaced:
    under pytest's capture, or a redirect into a StringIO, `reconfigure` is
    simply absent, and a report that is already readable there needs nothing
    from us. `errors="replace"` for the same reason - a console that still
    cannot render a character should lose the character, not the report.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # A detached or already-closed stream. Printing is the caller's
            # problem then; failing to print is not worth an exception here.
            pass
