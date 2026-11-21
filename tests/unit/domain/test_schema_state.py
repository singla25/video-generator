"""BL-8 SS-D*: ``classify(current, expected)`` in vidgen.domain.schema_state (pure)."""

from __future__ import annotations

import pytest

from tests.fixtures.schema_doubles import value
from vidgen.domain.schema_state import classify


@pytest.mark.parametrize(
    ("current", "expected", "state"),
    [
        ("0003", "0003", "ok"),
        ("0001", "0001", "ok"),
        ("0002", "0003", "behind"),
        ("0001", "0003", "behind"),
        ("0004", "0003", "ahead"),
        ("0010", "0003", "ahead"),
        (None, "0003", "empty"),
    ],
)
def test_classify_compares_revisions(current: str | None, expected: str, state: str) -> None:
    """SS-D-P1: equal is ok, older is behind, newer is ahead, none is empty."""
    assert value(classify(current, expected)) == state


@pytest.mark.parametrize("current", ["head", "abc123", "0002_x", "", "  "])
def test_classify_non_numeric_current_counts_as_behind(current: str) -> None:
    """SS-D-N1: an unknown revision id needs a look, so it is behind (never ok)."""
    assert value(classify(current, "0003")) == "behind"


def test_classify_compares_numbers_not_text() -> None:
    """SS-D-E1: different zero-padding still compares by number ('3' == '0003', '10' > '9')."""
    assert value(classify("3", "0003")) == "ok"
    assert value(classify("10", "0009")) == "ahead"
    assert value(classify("9", "0010")) == "behind"


def test_classify_is_pure_and_repeatable() -> None:
    """SS-D-E2: the same input always gives the same answer."""
    assert value(classify("0002", "0003")) == value(classify("0002", "0003"))
