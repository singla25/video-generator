"""Shared plumbing of the batch services: context, loading, audit and view building."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from vidgen.domain.codes import FailureCode
from vidgen.domain.naming import resolve_folder_name, unique_folder_name
from vidgen.domain.progress import pending_stage_label
from vidgen.domain.providers import (
    DataClass,
    ProviderRegistry,
    UnknownProviderError,
    pause_reason,
)
from vidgen.domain.stats import StatusCounts
from vidgen.domain.status import (
    BatchAction,
    BatchState,
    IllegalTransitionError,
    PreviewGate,
    apply_batch_action,
    can_start,
)
from vidgen.ports import Clock, SheetReader, Storage, TemplateRecord, Transliterator, UnitOfWork
from vidgen.ports.batches import PREVIEW_PENDING, PREVIEW_READY, BatchRecord, JobQueue
from vidgen.ports.progress import StageReporter
from vidgen.ports.providers import QueueHeartbeats
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
logger = logging.getLogger(__name__)


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
    transliterator: Transliterator | None = None  # suggests the spoken name for the preview row
    require_spelling: bool = False  # local mode: a human confirms the spelling before approval
    spoken_script: str = "devanagari"
    stage_reporter: StageReporter | None = None  # live preview stage; None = no progress shown
    providers: ProviderRegistry | None = None  # render providers; None = legacy single queue
    queue_heartbeats: QueueHeartbeats | None = None  # per-queue worker liveness
    provider_env: Mapping[str, str] = field(default_factory=dict)  # for a provider's requires_env
    row_timeout_seconds: int = 600  # worst case of one row, for the spend-cap pause reason


def queue_name_for(ctx: BatchContext, batch: BatchRecord) -> str | None:
    """The batch provider's queue; None (default queue, legacy call shape) without a provider."""
    if batch.provider_id is None or ctx.providers is None:
        return None
    provider = ctx.providers.get(batch.provider_id)
    return None if provider is None else provider.queue


def enqueue_rows(ctx: BatchContext, batch: BatchRecord, row_ids: list[UUID]) -> None:
    """Hand row jobs to the batch provider's queue (no queue name for old batches)."""
    name = queue_name_for(ctx, batch)
    if name is None:
        ctx.queue.enqueue_rows(batch.id, row_ids)
    else:
        ctx.queue.enqueue_rows(batch.id, row_ids, queue_name=name)


def queue_spellings(ctx: BatchContext, batch_id: UUID) -> None:
    """Queue the spelling job in local mode; a queue error never fails the preview."""
    if ctx.transliterator is None or not ctx.require_spelling:
        return
    try:
        ctx.queue.enqueue_spellings(batch_id)
    except Exception as exc:
        logger.warning(
            "spelling job not queued",
            extra={"error_type": type(exc).__name__, "batch_id": str(batch_id)},
        )


def provider_pause_reason(ctx: BatchContext, uow: UnitOfWork, batch: BatchRecord) -> str | None:
    """Why a PAUSED batch is paused by its provider (data class or spend cap), else None."""
    if batch.status != BatchState.PAUSED.value or ctx.providers is None:
        return None
    try:
        provider = ctx.providers.for_batch(batch.provider_id)
    except UnknownProviderError:
        return None
    spent = uow.batches.provider_spent(provider.id, ctx.providers.is_default(provider))
    return pause_reason(
        batch.status, provider, DataClass(batch.data_class), spent, ctx.row_timeout_seconds
    )


def pick_folder(ctx: BatchContext, used: set[str], custom: str | None, live_rows: int) -> str:
    """A folder name no batch and no stored folder uses yet (R6.2)."""
    base = resolve_folder_name(custom, ctx.clock.now().date(), live_rows)
    taken = set(used)
    while True:
        candidate = unique_folder_name(base, taken)
        if not ctx.storage.folder_exists(candidate):
            return candidate
        taken.add(candidate)


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
    ctx: BatchContext,
    uow: UnitOfWork,
    batch: BatchRecord,
    *,
    counts: StatusCounts | None = None,
    report: BatchReport | None = None,
    queued_rows: int | None = None,
    retried_rows: int | None = None,
    suggested_spoken_name: str | None = None,
    spelling_required: bool = False,
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
        suggested_spoken_name=suggested_spoken_name,
        spelling_required=spelling_required,
        spent_usd=uow.batches.batch_spent(batch.id),
        pause_reason=provider_pause_reason(ctx, uow, batch),
    )


def describe_preview(ctx: BatchContext, uow: UnitOfWork, batch: BatchRecord) -> BatchView:
    """A batch view with the spoken-name suggestion (local mode) and the live preview stage."""
    if not ctx.require_spelling:
        view = describe(ctx, uow, batch)  # fake mode: the preview keeps its original shape
    else:
        view = describe(
            ctx,
            uow,
            batch,
            suggested_spoken_name=suggest_spoken_name(ctx, uow, batch),
            spelling_required=True,
        )
    return replace(view, preview_stage=read_preview_stage(ctx, batch))


def read_preview_stage(ctx: BatchContext, batch: BatchRecord) -> str | None:
    """The label of a pending preview's stage, or None for any other preview state.

    Progress is best-effort: if the stage store fails, the page still loads and shows "preparing".
    The error text is not logged because it can carry the connection string.
    """
    if batch.preview.status != PREVIEW_PENDING:
        return None
    raw: str | None = None
    if ctx.stage_reporter is not None:
        try:
            raw = ctx.stage_reporter.current(batch.id)
        except Exception as exc:
            logger.warning(
                "preview stage unavailable",
                extra={"error_type": type(exc).__name__, "batch_id": str(batch.id)},
            )
    return pending_stage_label(raw)


def suggest_spoken_name(ctx: BatchContext, uow: UnitOfWork, batch: BatchRecord) -> str | None:
    """The transliterator's guess for the preview row (never logged), or None."""
    preview = batch.preview
    if ctx.transliterator is None or preview.row_id is None or preview.status != PREVIEW_READY:
        return None
    if preview.spoken_name is not None:
        return None  # already confirmed: no need to run the model again
    row = uow.batches.get_row_by_id(batch.id, preview.row_id)
    if row is None:
        return None
    base = (row.spoken_name or row.name).strip()
    return ctx.transliterator.transliterate(base, ctx.spoken_script) or None
