"""Static checks of the CI workflow file: speed choices that must not silently disappear."""

from __future__ import annotations

import re

from tests.unit.meta.conftest import ROOT

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _job_block(name: str) -> str:
    """The text of one top-level job (from its ``  name:`` line to the next job)."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)", _text(), re.M | re.S)
    assert match, f"job {name} not found"
    return match.group(1)


def test_e2e_job_runs_in_parallel_with_the_other_jobs() -> None:
    """The end-to-end job only needs its own services, so it must not wait for the others."""
    assert not re.search(r"^    needs:", _job_block("e2e"), re.M)


def test_pytest_prints_the_slowest_tests() -> None:
    """``--durations`` keeps the slowest tests visible in every CI log."""
    assert re.search(r"pytest .*--durations=\d+", _job_block("python"))


def test_pytest_still_runs_in_parallel() -> None:
    """The xdist setting (PR #41) stays."""
    assert "-n auto" in _job_block("python")


def test_superseded_runs_are_cancelled() -> None:
    """A new push cancels the older run of the same branch."""
    assert re.search(r"^concurrency:\n(?:  .*\n)*?  cancel-in-progress: true", _text(), re.M)
