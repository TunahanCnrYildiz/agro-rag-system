"""TEMPORARY: proves CI actually fails on a failing test. Deleted immediately."""


def test_ci_must_go_red():
    assert 1 == 2, "deliberate failure to verify CI reports red"
