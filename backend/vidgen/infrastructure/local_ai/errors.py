"""Errors raised by the local AI adapters. Each one is stored as a row failure, never a crash."""

from __future__ import annotations


class LocalAiError(Exception):
    """Base class for every local-AI failure."""


class ModelWeightsMissingError(LocalAiError):
    """The model folder does not exist or is empty."""


class EmptyAudioError(LocalAiError):
    """An audio input holds no samples."""


class OfflineViolationError(LocalAiError):
    """Code tried to reach the network while the offline guard was active."""


class AiBusyError(LocalAiError):
    """Another memory-heavy render is already running."""


class NameSlotNotFoundError(LocalAiError):
    """The name could not be located in the transcript and no manual slot was given."""
