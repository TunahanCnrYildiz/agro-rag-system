"""Shared pytest fixtures."""

import sys

import pytest

from evals import answer_log


@pytest.fixture(autouse=True)
def _isolate_answer_log(tmp_path, monkeypatch):
    """Keep the suite from littering the real evals/runs/ directory.

    The answer log is always-on in run()/run_faithfulness(), and this suite calls
    both dozens of times. Tests that inspect the log patch RUNS_DIR themselves;
    this fixture just guarantees nothing lands in the repo.
    """
    monkeypatch.setattr(answer_log, "RUNS_DIR", tmp_path / "runs")


@pytest.fixture(autouse=True)
def _fresh_chat_rate_limit():
    """`src/main.py` holds ONE rate limiter for the process, so without this
    every test in the suite spends from the same ceiling and the suite passes
    only while it stays under it. It makes 20 chat requests today against 60 -
    green by accident of the current test count, not by construction.

    Reached through `sys.modules` so this fixture does not import the app for
    the many tests that never touch it.
    """
    module = sys.modules.get("src.main")
    if module is not None:
        module._chat_limit.reset()
    yield
