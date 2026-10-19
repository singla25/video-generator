"""Shared plumbing of the batch services: context, loading, audit and view building."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from vidgen.domain.codes import FailureCode
from vidgen.domain.stats import StatusCounts
from vidgen.domain.status import (
    BatchAction,
    BatchState,
    IllegalTransitionError,
    PreviewGate,
    apply_batch_action,
    can_start,
)
from vidgen.ports import Clock, SheetReader, Storage, TemplateRecord, UnitOfWork
from vidgen.ports.batches import PREVIEW_READY, BatchRecord, JobQueue
from vidgen.services.audit import ACTOR_ADMIN, UowFactory
from vidgen.services.batch_rules import counts_from, fingerprint_for
from vidgen.services.batch_views import BatchReport, BatchView
from vidgen.services.errors import (
    BatchNotFoundError,
    PreconditionError,
    StateConflictError,
    TemplateNotFoundError,
)

PREVIEW_STALE = "STALE"  # a preview exists but belongs to an earlier slot/template/mapping


@dataclass(frozen=True)
class BatchContext:
    """Everything the batch services share."""

    uow: UowFactory
    storage: Storage
    clock: Clock
    queue: JobQueue
    reader: SheetReader
    max_sheet_rows: int
    max_name_graphemes: int
    retention_days: int


def load_batch(uow: UnitOfWork, batch_id: UUID, *, lock: bool = False) -> BatchRecord:
    """The batch, or BatchNotFoundError."""
    batch = uow.batches.get(batch_id, lock=lock)
    if batch is None:
        raise BatchNotFoundError
    return batch


def load_template(uow: UnitOfWork, template_id: UUID) -> TemplateRecord:
    """The template, or TemplateNotFoundError."""
    template = uow.templates.get(template_id)
    if template is None:
        raise TemplateNotFoundError
    return template


def ensure_usable(template: TemplateRecord) -> None:
    """A template needs consent and a confirmed slot before a batch can use it (D-16)."""
    if not template.consent_confirmed:
        raise PreconditionError(FailureCode.CONSENT_MISSING)
    if not template.slot_confirmed:
        raise PreconditionError(FailureCode.SLOT_NOT_FOUND)


def transition(batch: BatchRecord, action: BatchAction) -> BatchState:
    """The batch's next state, or StateConflictError if the action is not allowed."""
    try:
        return apply_batch_action(BatchState(batch.status), action)
    except IllegalTransitionError:
        raise StateConflictError(StateConflictError.INVALID_STATE) from None


def preview_gate(batch: BatchRecord) -> PreviewGate:
    """The preview state as the domain's approval gate."""
    preview = batch.preview
    rendered = preview.rendered_for if preview.status == PREVIEW_READY else None
    return PreviewGate(rendered_for=rendered, approved_for=preview.approved_for)


def audit(
    ctx: BatchContext, uow: UnitOfWork, action: str, *, actor: str = ACTOR_ADMIN, **details: Any
) -> None:
    """Append an audit entry (ids and counts only)."""
    uow.audit.add(
        campaign_id=uow.campaign_id,
        actor=actor,
        action=action,
        at=ctx.clock.now(),
        details=details,
    )


def describe(
    uow: UnitOfWork,
    batch: BatchRecord,
    *,
    counts: StatusCounts | None = None,
    report: BatchReport | None = None,
    queued_rows: int | None = None,
    retried_rows: int | None = None,
) -> BatchView:
    """A batch with counts, success rate and the preview state as the user sees it."""
    counts = counts or counts_from(uow.batches.counts([batch.id])[batch.id])
    template = load_template(uow, batch.template_id)
    current = fingerprint_for(template, batch.mapping)
    preview_status = batch.preview.status
    if preview_status == PREVIEW_READY and batch.preview.rendered_for != current:
        preview_status = PREVIEW_STALE
    finished = counts.completed + counts.failed
    return BatchView(
        record=batch,
        counts=counts,
        success_rate=counts.completed / finished if finished else None,
        preview_status=preview_status,
        preview_approved=can_start(preview_gate(batch), current),
        report=report,
        queued_rows=queued_rows,
        retried_rows=retried_rows,
    )
