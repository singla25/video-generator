"""Package-level rules for the real-AI adapters (M2 plan AC10, D-M2-3)."""

from __future__ import annotations

import importlib
import sys

import pytest

from vidgen.domain.codes import DomainError, FailureCode

HEAVY = ("torch", "faster_whisper", "demucs", "chatterbox", "transformers", "ctranslate2")
MODULES = [
    "faster_whisper_stt",
    "qwen_transliterator",
    "chatterbox_cloner",
    "musetalk_lipsyncer",
    "demucs_separator",
]


@pytest.mark.parametrize("name", MODULES)
def test_importing_an_adapter_never_imports_a_model_library(name: str) -> None:
    """M2-S6-P1: models load lazily at first use, never at import (so CPU CI stays light)."""
    before = {m for m in HEAVY if m in sys.modules}
    importlib.import_module(f"vidgen.infrastructure.ai.{name}")
    after = {m for m in HEAVY if m in sys.modules}
    assert after == before


def test_model_load_error_is_a_domain_error_with_the_given_code() -> None:
    """M2-S6-P2."""
    from vidgen.infrastructure.ai.errors import ModelLoadError

    error = ModelLoadError(FailureCode.TTS_FAILED, "weights missing")
    assert isinstance(error, DomainError)
    assert error.code is FailureCode.TTS_FAILED


def test_adapter_timeout_error_is_retryable() -> None:
    """M2-S6-P3: RENDER_TIMEOUT is in the retryable set (worker crash/timeout is retry-safe)."""
    from vidgen.domain.codes import is_retryable
    from vidgen.infrastructure.ai.errors import AdapterTimeoutError

    error = AdapterTimeoutError("took too long")
    assert error.code is FailureCode.RENDER_TIMEOUT
    assert is_retryable(error.code)
