"""Find where the name is spoken in the template transcript (AC4)."""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Literal

from vidgen.domain.values import Word
from vidgen.infrastructure.local_ai.errors import NameSlotNotFoundError

DEFAULT_MIN_CONFIDENCE = 0.6


@dataclass(frozen=True)
class NameSlot:
    """The time span of the spoken name and how it was found."""

    start_s: float
    end_s: float
    source: Literal["auto", "manual"]
    ambiguous: bool


def _normal(text: str) -> str:
    """Lower-case and strip surrounding punctuation."""
    return text.strip().strip(string.punctuation + "।॥").casefold()


def detect_name_slot(
    words: list[Word],
    placeholder: str,
    manual: tuple[float, float] | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> NameSlot:
    """Locate ``placeholder`` in ``words``; a manual slot wins; ambiguity is flagged for review."""
    if manual is not None:
        if manual[1] <= manual[0]:
            raise ValueError("manual slot must end after it starts")
        return NameSlot(manual[0], manual[1], "manual", ambiguous=False)
    target = _normal(placeholder)
    hits = [word for word in words if _normal(word.text) == target]
    if not hits:
        raise NameSlotNotFoundError(f"'{placeholder}' not found in the transcript; mark it by hand")
    first = hits[0]
    ambiguous = len(hits) > 1 or first.confidence < min_confidence
    return NameSlot(first.start_s, first.end_s, "auto", ambiguous=ambiguous)
