"""Ports and data used by the per-row render pipeline (T14).

Pure data and Protocols: no I/O and no framework imports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol
from uuid import UUID

from vidgen.domain.codes import FailureCode
from vidgen.domain.outcomes import RowOutcomeKind
from vidgen.domain.slot_match import Slot, all_slots
from vidgen.ports.batches import RowView


class ClaimAction(Enum):
    """What the store must do with a row it has locked."""

    CLAIM = "claim"  # mark PROCESSING and count the attempt
    CANCEL_ROW = "cancel_row"  # the batch was cancelled: mark the queued row CANCELLED
    LEAVE = "leave"  # change nothing


@dataclass(frozen=True)
class ClaimSnapshot:
    """The facts a claim decision depends on."""

    batch_status: str
    row_status: str
    started_at: datetime | None


@dataclass(frozen=True)
class ClaimDecision:
    """The decision: an action and, when the row is not claimed, the outcome to report."""

    action: ClaimAction
    outcome: RowOutcomeKind


@dataclass(frozen=True)
class Completion:
    """What to do with the batch once a row has finished."""

    new_status: str | None
    write_manifest: bool


@dataclass(frozen=True)
class TemplateInfo:
    """The template facts the pipeline needs."""

    video_key: str
    width: int
    height: int
    slot: tuple[float, float] | None
    slot_confirmed: bool
    consent_confirmed: bool
    extra_slots: tuple[Slot, ...] = ()

    @property
    def slots(self) -> tuple[Slot, ...]:
        """Every slot sorted by start: the primary plus the extras; () without a primary."""
        return all_slots(self.slot, self.extra_slots)


@dataclass(frozen=True)
class RowJob:
    """A claimed row with its personal data decrypted. Never log or serialise this."""

    batch_id: UUID
    row_id: UUID
    row_number: int
    name: str
    spoken_name: str | None
    voter_id: str
    attempts: int
    folder_name: str
    template: TemplateInfo
    provider_id: str | None = None  # the batch's provider; None = the default provider


@dataclass(frozen=True)
class ClaimResult:
    """Outcome of a claim: a job to render, or the outcome to report."""

    outcome: RowOutcomeKind
    job: RowJob | None


@dataclass(frozen=True)
class RowUpdate:
    """The final or intermediate state to store on a row."""

    status: str
    failure_code: str | None = None
    output_key: str | None = None
    render_seconds: float | None = None
    cost_usd: float | None = None  # measured cost of the row; None = not measured


@dataclass(frozen=True)
class ManifestInput:
    """Everything needed to write a batch's manifest."""

    folder_name: str
    rows: list[RowView]


SpendLookup = Callable[[str, bool], float]
"""``(provider_id, include_unrouted) -> USD spent`` by that provider so far."""


class ProviderGate(Protocol):
    """Worker-side provider rules (C5 and the spend cap), asked inside the claim transaction."""

    def pause_reason(
        self, provider_id: str | None, data_class: str, spent: SpendLookup
    ) -> str | None:
        """Why the batch must pause before this row starts, or None to go ahead."""
        ...


class RowStore(Protocol):
    """Row claiming and completion in one transaction each, with row-level locks."""

    def claim(
        self,
        batch_id: UUID,
        row_id: UUID,
        decide: Callable[[ClaimSnapshot], ClaimDecision],
        now: datetime,
        gate: ProviderGate | None = None,
    ) -> ClaimResult:
        """Lock the row (skipping locked ones), apply ``decide`` and return the result.

        With a ``gate``, a QUEUED row of a RUNNING batch is first checked against the provider
        rules; on a refusal the batch is PAUSED, the row is left untouched and DEFERRED returned.
        """
        ...

    def preview_job(self, batch_id: UUID, row_id: UUID) -> RowJob | None:
        """The row as a job for a preview render; None if the batch or row is gone."""
        ...

    def finish(
        self,
        batch_id: UUID,
        row_id: UUID,
        update: RowUpdate,
        now: datetime,
        decide_completion: Callable[[str, int], Completion],
    ) -> ManifestInput | None:
        """Store ``update``; if the batch is done, complete it and return the manifest data."""
        ...


@dataclass(frozen=True)
class MissingSpelling:
    """A QUEUED row that has no spoken name yet. ``name`` is decrypted: never log it."""

    row_id: UUID
    row_number: int
    name: str


class SpellingStore(Protocol):
    """Reads and writes the spoken spellings the spelling job suggests (BL-11)."""

    def rows_missing_spoken_name(
        self, batch_id: UUID, after: int, limit: int
    ) -> list[MissingSpelling]:
        """QUEUED rows without a spoken name, row number above ``after``, ascending."""
        ...

    def set_spoken_name(self, row_id: UUID, spoken: str) -> bool:
        """Store ``spoken`` encrypted if the row is still QUEUED and has none; True if stored."""
        ...


class PreviewSink(Protocol):
    """Receives the result of a preview render."""

    def preview_rendered(self, batch_id: UUID, key: str) -> None:
        """The preview is stored at ``key``."""
        ...

    def preview_failed(self, batch_id: UUID, code: FailureCode) -> None:
        """The preview could not be rendered."""
        ...
