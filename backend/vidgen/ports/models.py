"""Plain data types exchanged through the ports. Pure: no I/O imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from vidgen.domain.slot_match import Slot, all_slots


@dataclass(frozen=True)
class SheetRow:
    """A non-blank data row; ``row_number`` is the sheet row (the header is row 1)."""

    row_number: int
    cells: list[str]


@dataclass(frozen=True)
class VideoLimits:
    """Accepted ranges for an uploaded video (from settings); bounds are inclusive."""

    max_bytes: int
    max_seconds: float
    min_seconds: float


@dataclass(frozen=True)
class VideoInfo:
    """Facts about an accepted video. Tags and other metadata are deliberately left out."""

    container: str
    video_codec: str
    audio_codec: str
    width: int
    height: int
    fps: float
    duration_s: float
    size_bytes: int

    @property
    def has_audio(self) -> bool:
        """True when an audio track exists (always true for an accepted video)."""
        return bool(self.audio_codec)


@dataclass
class TemplateRecord:
    """A template and its analysed profile as the services see it."""

    id: UUID
    video_key: str
    original_name: str
    duration_s: float
    width: int
    height: int
    slot_start_s: float | None = None
    slot_end_s: float | None = None
    slot_source: str | None = None
    slot_confidence: float | None = None
    slot_confirmed: bool = False
    slot_error: str | None = None
    analysed_at: datetime | None = None
    consent_confirmed: bool = False
    created_at: datetime | None = None
    extra_slots: tuple[Slot, ...] = ()

    @property
    def slot(self) -> tuple[float, float] | None:
        """The slot (start, end) in seconds, or None if none is set."""
        if self.slot_start_s is None or self.slot_end_s is None:
            return None
        return (self.slot_start_s, self.slot_end_s)

    @property
    def slots(self) -> tuple[Slot, ...]:
        """Every slot sorted by start: the primary plus the extras; () without a primary."""
        return all_slots(self.slot, self.extra_slots)

    @property
    def usable(self) -> bool:
        """A template can be used for a batch once consent and the slot are confirmed (D-16)."""
        return self.consent_confirmed and self.slot_confirmed

    @property
    def needs_manual_slot(self) -> bool:
        """True when analysis ran but found no slot, so the user must mark one."""
        return self.analysed_at is not None and self.slot is None


@dataclass(frozen=True)
class AuditEntry:
    """One audit log entry. ``details`` never holds personal data (C5)."""

    at: datetime
    actor: str
    action: str
    details: dict[str, Any]
