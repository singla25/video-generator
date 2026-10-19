"""Deterministic fake AI adapters used while ``ai_backend=fake`` (ADR-008)."""

from vidgen.infrastructure.fakes.adapters import (
    FakeLipSyncer,
    FakeQualityChecker,
    FakeSpeechToText,
    FakeVoiceCloner,
)

__all__ = ["FakeLipSyncer", "FakeQualityChecker", "FakeSpeechToText", "FakeVoiceCloner"]
