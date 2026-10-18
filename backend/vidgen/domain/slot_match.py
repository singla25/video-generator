"""Target-word selection, manual slot validation and the content lock (AC6, AC18, C3, C6)."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Sequence

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.timing import EPSILON_S
from vidgen.domain.values import Word


class InvalidSlotError(DomainError):
    """A manual slot is not a finite, ordered range inside the video."""

    def __init__(self) -> None:
        super().__init__(FailureCode.SLOT_NOT_FOUND)


class ContentLockViolationError(DomainError):
    """A planned change touches video outside the confirmed slot."""

    def __init__(self) -> None:
        super().__init__(FailureCode.CONTENT_LOCK_VIOLATION)


def _strip_punctuation(text: str) -> str:
    """Remove punctuation at both ends. Category check keeps Devanagari vowel signs intact."""
    punctuation = "".join(c for c in set(text) if unicodedata.category(c).startswith("P"))
    return text.strip(punctuation)


def _normalise_word(text: str) -> str:
    """Comparison form of a spoken word: NFC, case-folded, no edge punctuation."""
    return _strip_punctuation(unicodedata.normalize("NFC", text.strip()).casefold())


def select_target_word(words: Iterable[Word], target: str, threshold: float) -> Word | None:
    """Best match for ``target``: highest confidence, then earliest; threshold inclusive (C3)."""
    wanted = _normalise_word(target)
    matches = [w for w in words if w.confidence >= threshold and _normalise_word(w.text) == wanted]
    return min(matches, key=lambda w: (-w.confidence, w.start_s), default=None)


def validate_slot(start_s: float, end_s: float, duration_s: float) -> None:
    """Raise InvalidSlotError unless 0 <= start < end <= duration, all finite."""
    finite = math.isfinite(start_s) and math.isfinite(end_s)
    if not (finite and 0 <= start_s < end_s <= duration_s):
        raise InvalidSlotError


def ensure_within_slot(
    slot: tuple[float, float], changed: Sequence[tuple[float, float]], extension_s: float = 0.0
) -> None:
    """Raise ContentLockViolationError if any changed range leaves the slot (plus extension)."""
    slot_start, slot_end = slot
    limit = slot_end + extension_s + EPSILON_S
    if any(start < slot_start - EPSILON_S or end > limit for start, end in changed):
        raise ContentLockViolationError
