"""Shared pytest fixtures."""

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
