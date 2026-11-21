"""The ``name_match_threshold`` setting: 0.8 by default, 0 to 1 (AC2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.unit.infra.test_name_gap_setting import build


def test_name_match_threshold_defaults_to_point_eight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDGEN_NAME_MATCH_THRESHOLD", raising=False)
    assert build().name_match_threshold == 0.8


def test_name_match_threshold_reads_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIDGEN_NAME_MATCH_THRESHOLD", "0.65")
    assert build().name_match_threshold == 0.65


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_name_match_threshold_accepts_the_range_ends(value: float) -> None:
    assert build(name_match_threshold=value).name_match_threshold == value


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_name_match_threshold_outside_zero_to_one_is_refused(value: float) -> None:
    with pytest.raises(ValidationError):
        build(name_match_threshold=value)


def test_name_match_threshold_not_a_number_is_refused() -> None:
    with pytest.raises(ValidationError):
        build(name_match_threshold="high")
