"""Preview gate, start and batch control (AC7, AC11, AC13, A5, A6, B4, B11, C2).

Every state change runs in one transaction with the batch row locked, so concurrent requests
(two starts, two retries) cannot queue a row twice. Jobs are handed to the queue after the
commit, so a worker never sees a state that might still be rolled back.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.naming import resolve_folder_name, unique_folder_name
from vidgen.domain.status import (
    BatchAction,
    BatchState,
    PreviewNotReadyError,
    approve_preview,
    can_start,
)
from vidgen.ports.batches import (
    PREVIEW_FAILED,
    PREVIEW_PENDING,
    PREVIEW_READY,
    PreviewRecord,
)
from vidgen.services.batch_rules import fingerprint_for
from vidgen.services.batch_support import (
    BatchContext,
    audit,
    describe,
    describe_preview,
    load_batch,
    load_template,
    preview_gate,
    transition,
)
from vidgen.services.batch_views import BatchView
from vidgen.services.errors import BatchNotFoundError, StateConflictError


class BatchFlow:
    """Preview, start and control of one batch at a time."""

    def __init__(self, ctx: BatchContext) -> None:
        self._ctx = ctx

    # ---- preview -----------------------------------------------------------------------

    def request_preview(self, batch_id: UUID) -> BatchView:
        """Queue the preview render of the first valid row; clears any earlier approval."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            row_id = uow.batches.first_live_row_id(batch_id)
            if batch.status != BatchState.DRAFT.value or row_id is None:
                raise StateConflictError(StateConflictError.INVALID_STATE)
            template = load_template(uow, batch.template_id)
            old_key = batch.preview.key
            # DD-38: the confirmed spelling outlives a regenerate; nothing else is carried over.
            batch = replace(
                batch,
                preview=PreviewRecord(
                    status=PREVIEW_PENDING,
                    row_id=row_id,
                    requested_for=fingerprint_for(template, batch.mapping),
                    spoken_name=batch.preview.spoken_name,
                ),
            )
            uow.batches.save(batch)
            audit(ctx, uow, "PREVIEW_REQUESTED", batch_id=str(batch_id))
            ctx.queue.enqueue_preview(batch_id, row_id)  # inside: a queue error rolls back
            uow.commit()
            view = describe_preview(ctx, uow, batch)
        if old_key:
            ctx.storage.delete(old_key)
        return view

    def approve_preview(self, batch_id: UUID) -> BatchView:
        """Approve the rendered preview for the current slot, template and mapping."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            current = fingerprint_for(load_template(uow, batch.template_id), batch.mapping)
            gate = preview_gate(batch)
            if not can_start(gate, current):
                if ctx.require_spelling and batch.preview.spoken_name is None:
                    raise StateConflictError(StateConflictError.SPELLING_NOT_CONFIRMED)
                try:
                    gate = approve_preview(gate, current)
                except PreviewNotReadyError:
                    raise StateConflictError(StateConflictError.PREVIEW_NOT_READY) from None
                batch = replace(
                    batch, preview=replace(batch.preview, approved_for=gate.approved_for)
                )
                uow.batches.save(batch)
                audit(ctx, uow, "PREVIEW_APPROVED", batch_id=str(batch_id))
                uow.commit()
            return describe_preview(ctx, uow, batch)

    def confirm_spelling(self, batch_id: UUID, spoken_name: str) -> BatchView:
        """Store the human-confirmed spoken name; any earlier approval is withdrawn."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            if batch.status != BatchState.DRAFT.value:
                raise StateConflictError(StateConflictError.INVALID_STATE)
            if batch.preview.status != PREVIEW_READY:
                raise StateConflictError(StateConflictError.PREVIEW_NOT_READY)
            preview = replace(batch.preview, spoken_name=spoken_name, approved_for=None)
            batch = replace(batch, preview=preview)
            uow.batches.save(batch)
            audit(ctx, uow, "SPOKEN_NAME_CONFIRMED", batch_id=str(batch_id))  # name never logged
            uow.commit()
            return describe_preview(ctx, uow, batch)

    def preview_rendered(self, batch_id: UUID, key: str) -> None:
        """Worker hook: the preview file is stored at ``key``."""
        with self._ctx.uow() as uow:
            batch = uow.batches.get(batch_id, lock=True)
            if batch is None:
                return  # deleted meanwhile: nothing to update
            preview = replace(
                batch.preview,
                status=PREVIEW_READY,
                key=key,
                failure_code=None,
                rendered_for=batch.preview.requested_for,
                approved_for=None,
            )
            uow.batches.save(replace(batch, preview=preview))
            uow.commit()

    def preview_failed(self, batch_id: UUID, code: FailureCode) -> None:
        """Worker hook: the preview could not be rendered."""
        with self._ctx.uow() as uow:
            batch = uow.batches.get(batch_id, lock=True)
            if batch is None:
                return
            preview = replace(batch.preview, status=PREVIEW_FAILED, failure_code=code.value)
            uow.batches.save(replace(batch, preview=preview))
            uow.commit()

    def preview_key(self, batch_id: UUID) -> str:
        """Storage key of the rendered preview, or PREVIEW_NOT_READY."""
        with self._ctx.uow() as uow:
            preview = load_batch(uow, batch_id).preview
        if preview.status != PREVIEW_READY or preview.key is None:
            raise StateConflictError(StateConflictError.PREVIEW_NOT_READY)
        return preview.key

    # ---- start -------------------------------------------------------------------------

    def start(
        self,
        batch_id: UUID,
        idempotency_key: str,
        folder_name: str | None,
        limit: int | None = None,
    ) -> BatchView:
        """Start a batch once; repeats and re-starts return the current state (B11, C2).

        With ``limit`` the first rows in sheet order stay QUEUED and the others are SKIPPED
        (NOT_SELECTED); the folder name counts only the selected rows (DD-37).
        """
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            owner = uow.batches.by_idempotency_key(idempotency_key)
            if owner is not None and owner != batch_id:
                raise DomainError(FailureCode.IDEMPOTENCY_KEY_CONFLICT)
            counts = uow.batches.counts([batch_id])[batch_id]
            live_rows = sum(counts.values()) - counts.get("SKIPPED", 0)
            if batch.status != BatchState.DRAFT.value:
                transition(batch, BatchAction.START)  # raises for finished batches
                return describe(uow, batch, queued_rows=live_rows)
            current = fingerprint_for(load_template(uow, batch.template_id), batch.mapping)
            if not can_start(preview_gate(batch), current):
                raise StateConflictError(StateConflictError.PREVIEW_NOT_APPROVED)
            skipped = uow.batches.skip_unselected(batch_id, limit) if limit is not None else 0
            row_ids = uow.batches.queued_row_ids(batch_id)
            folder = self._pick_folder(uow.batches.folders_in_use(), folder_name, len(row_ids))
            now = ctx.clock.now()
            batch = replace(
                batch,
                status=transition(batch, BatchAction.START).value,
                started_at=now,
                idempotency_key=idempotency_key,
                folder_name=folder,
            )
            uow.batches.save(batch)
            audit(
                ctx,
                uow,
                "BATCH_STARTED",
                batch_id=str(batch_id),
                queued_rows=len(row_ids),
                limit=limit,
                skipped_rows=skipped,
            )
            uow.commit()
            view = describe(uow, batch, queued_rows=len(row_ids))
        ctx.queue.enqueue_rows(batch_id, row_ids)
        return view

    def _pick_folder(self, used: set[str], custom: str | None, live_rows: int) -> str:
        """A folder name no batch and no stored folder uses yet (R6.2)."""
        base = resolve_folder_name(custom, self._ctx.clock.now().date(), live_rows)
        taken = set(used)
        while True:
            candidate = unique_folder_name(base, taken)
            if not self._ctx.storage.folder_exists(candidate):
                return candidate
            taken.add(candidate)

    # ---- control -----------------------------------------------------------------------

    def pause(self, batch_id: UUID) -> BatchView:
        """Stop new rows from starting."""
        return self._change(batch_id, BatchAction.PAUSE, "BATCH_PAUSED")

    def resume(self, batch_id: UUID) -> BatchView:
        """Let a paused batch continue."""
        return self._change(batch_id, BatchAction.RESUME, "BATCH_RESUMED")

    def cancel(self, batch_id: UUID) -> BatchView:
        """Cancel the queued rows; rows already processing finish (A6)."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            new_state = transition(batch, BatchAction.CANCEL)
            if new_state.value != batch.status:
                now = ctx.clock.now()
                cancelled = uow.batches.cancel_queued(batch_id, now)
                batch = replace(batch, status=new_state.value, finished_at=now)
                uow.batches.save(batch)
                audit(ctx, uow, "BATCH_CANCELLED", batch_id=str(batch_id), cancelled_rows=cancelled)
                uow.commit()
            return describe(uow, batch)

    def retry_failed(self, batch_id: UUID) -> BatchView:
        """Queue the failed rows again; a finished batch runs again."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            new_state = transition(batch, BatchAction.RETRY)
            row_ids = uow.batches.requeue_failed(batch_id)
            if row_ids:
                batch = replace(
                    batch,
                    status=new_state.value,
                    finished_at=None if new_state is BatchState.RUNNING else batch.finished_at,
                )
                uow.batches.save(batch)
                audit(ctx, uow, "BATCH_RETRIED", batch_id=str(batch_id), retried_rows=len(row_ids))
                uow.commit()
            view = describe(uow, batch, retried_rows=len(row_ids))
        if row_ids:
            ctx.queue.enqueue_rows(batch_id, row_ids)
        return view

    def retry_row(self, batch_id: UUID, row_number: int) -> BatchView:
        """Queue one failed row again; anything else is refused without side effects."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            if uow.batches.get_row(batch_id, row_number) is None:
                raise BatchNotFoundError
            new_state = transition(batch, BatchAction.RETRY)
            row_id = uow.batches.requeue_row(batch_id, row_number)
            if row_id is None:
                raise StateConflictError(StateConflictError.INVALID_STATE)
            batch = replace(
                batch,
                status=new_state.value,
                finished_at=None if new_state is BatchState.RUNNING else batch.finished_at,
            )
            uow.batches.save(batch)
            audit(ctx, uow, "ROW_RETRY", batch_id=str(batch_id), row_number=row_number)
            uow.commit()
            view = describe(uow, batch, retried_rows=1)
        ctx.queue.enqueue_rows(batch_id, [row_id])
        return view

    def _change(self, batch_id: UUID, action: BatchAction, event: str) -> BatchView:
        """Apply a plain state change; repeating it is a no-op (idempotent)."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            new_state = transition(batch, action)
            if new_state.value != batch.status:
                batch = replace(batch, status=new_state.value)
                uow.batches.save(batch)
                audit(ctx, uow, event, batch_id=str(batch_id))
                uow.commit()
            return describe(uow, batch)
