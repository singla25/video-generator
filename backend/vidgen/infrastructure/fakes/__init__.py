"""Deterministic fake AI adapters used while ``ai_mode=fake`` (ADR-008)."""

from vidgen.infrastructure.fakes.adapters import (
    FakeLipSyncer,
    FakeQualityChecker,
    FakeSpeechToText,
    FakeTransliterator,
    FakeVoiceCloner,
)

__all__ = [
    "FakeLipSyncer",
    "FakeQualityChecker",
    "FakeSpeechToText",
    "FakeTransliterator",
    "FakeVoiceCloner",
]
