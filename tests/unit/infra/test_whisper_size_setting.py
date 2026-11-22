"""The ``whisper_size`` and ``modal_whisper_size`` settings: small locally, medium on the GPU."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.unit.infra.test_name_gap_setting import build


def test_whisper_size_defaults_to_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDGEN_WHISPER_SIZE", raising=False)
    assert build().whisper_size == "small"


def test_modal_whisper_size_defaults_to_medium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDGEN_MODAL_WHISPER_SIZE", raising=False)
    assert build().modal_whisper_size == "medium"


@pytest.mark.parametrize("value", ["small", "medium"])
def test_whisper_size_reads_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("VIDGEN_WHISPER_SIZE", value)
    assert build().whisper_size == value


@pytest.mark.parametrize("value", ["small", "medium"])
def test_modal_whisper_size_reads_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("VIDGEN_MODAL_WHISPER_SIZE", value)
    assert build().modal_whisper_size == value


@pytest.mark.parametrize("field", ["whisper_size", "modal_whisper_size"])
@pytest.mark.parametrize("value", ["large", "tiny", "", "Medium", " small", "1"])
def test_unknown_whisper_size_is_refused_and_names_the_field(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        build(**{field: value})


def test_unknown_whisper_size_in_the_environment_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIDGEN_WHISPER_SIZE", "huge")
    with pytest.raises(ValidationError, match="whisper_size"):
        build()


def test_the_two_sizes_are_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDGEN_WHISPER_SIZE", raising=False)
    monkeypatch.delenv("VIDGEN_MODAL_WHISPER_SIZE", raising=False)
    settings = build(modal_whisper_size="small")
    assert (settings.whisper_size, settings.modal_whisper_size) == ("small", "small")
