"""Row job outcomes (what one delivery of a row job led to)."""

from __future__ import annotations

import pytest

from vidgen.domain.outcomes import RowOutcomeKind


def test_all_six_outcomes_exist_with_stable_values() -> None:
    """The kinds are part of the worker contract."""
    assert {kind.name: kind.value for kind in RowOutcomeKind} == {
        "COMPLETED": "completed",
        "FAILED": "failed",
        "RETRY": "retry",
        "NOOP": "noop",
        "BUSY": "busy",
        "DEFERRED": "deferred",
    }


@pytest.mark.parametrize("kind", list(RowOutcomeKind))
def test_outcomes_round_trip_through_their_values(kind: RowOutcomeKind) -> None:
    """Values can be stored or logged and read back."""
    assert RowOutcomeKind(kind.value) is kind


def test_unknown_value_is_refused() -> None:
    """No silent fallbacks."""
    with pytest.raises(ValueError, match="nonsense"):
        RowOutcomeKind("nonsense")
