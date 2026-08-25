"""Unit tests for scripts/_console.py.

The bug this guards against was not a wrong figure, it was a DEAD REPORT: on a
cp1252 console `print("HİGRO BARF")` raised, and it raised inside the block that
names every panel the parser could not read. So these tests are about the report
surviving, not about encoding for its own sake.
"""

import io

import pytest

from scripts._console import use_utf8_console


TURKISH = "HİGRO BARF / Kg/Meyve Veren Ağaç"


class _Cp1252Stream(io.TextIOWrapper):
    """A stdout shaped like the one Windows hands a piped script."""

    def __init__(self):
        super().__init__(io.BytesIO(), encoding="cp1252", errors="strict")


def test_a_turkish_name_raises_before_the_fix():
    """The premise. If this ever stops raising, the fix has nothing to guard."""
    stream = _Cp1252Stream()
    with pytest.raises(UnicodeEncodeError):
        print(TURKISH, file=stream)


def test_a_turkish_name_survives_after_the_fix(monkeypatch):
    stream = _Cp1252Stream()
    monkeypatch.setattr("sys.stdout", stream)
    use_utf8_console()
    print(TURKISH, file=stream)
    stream.flush()
    assert stream.buffer.getvalue().decode("utf-8").strip() == TURKISH


def test_stderr_is_reconfigured_too(monkeypatch):
    """build_crop_norms prints its skipped rows to stderr, where Python's
    `backslashreplace` turns 'Ağaç' into 'A\u011fa?' instead of raising - no
    crash, and no readable report either."""
    stream = _Cp1252Stream()
    monkeypatch.setattr("sys.stderr", stream)
    use_utf8_console()
    print(TURKISH, file=stream)
    stream.flush()
    assert stream.buffer.getvalue().decode("utf-8").strip() == TURKISH


def test_a_stream_without_reconfigure_is_left_alone(monkeypatch):
    """pytest's capture and a plain StringIO have no `reconfigure`. Neither
    needs one, and neither may be replaced - swapping sys.stdout out from under
    a caller would lose whatever it was pointing at."""
    plain = io.StringIO()
    monkeypatch.setattr("sys.stdout", plain)
    use_utf8_console()
    import sys
    assert sys.stdout is plain
    print(TURKISH, file=sys.stdout)
    assert plain.getvalue().strip() == TURKISH


def test_a_detached_stream_does_not_take_the_script_down(monkeypatch):
    """A closed stdout must not turn a finished build into a traceback - the
    whole point is that reporting never kills the run."""
    class _Broken:
        def reconfigure(self, **kwargs):
            raise ValueError("underlying buffer has been detached")

    monkeypatch.setattr("sys.stdout", _Broken())
    use_utf8_console()      # must not raise
