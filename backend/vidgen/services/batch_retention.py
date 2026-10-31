"""Batch deletion and the retention job (AC17, A8, B12, C5)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from vidgen.services.audit import ACTOR_ADMIN, ACTOR_SYSTEM
from vidgen.services.batch_support import BatchContext, audit
from vidgen.services.errors import BatchNotFoundError
from vidgen.services.storage_cleanup import delete_stored

REASON_RETENTION = "retention"
MANIFEST_NAME = "manifest.csv"  # written by the worker; it holds personal data (A7)


class BatchRetention:
    """Removes batches with their rows, files and personal data."""

    def __init__(self, ctx: BatchContext) -> None:
        self._ctx = ctx

    def delete(
        self, batch_id: UUID, *, actor: str = ACTOR_ADMIN, reason: str | None = None
    ) -> None:
        """Delete a batch: database rows first, then every stored file (sheet, preview, outputs)."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = uow.batches.get(batch_id, lock=True)
            if batch is None:
                raise BatchNotFoundError
            manifest = f"{batch.folder_name}/{MANIFEST_NAME}" if batch.folder_name else None
            keys = [
                batch.sheet_key,
                batch.preview.key,
                manifest,
                *uow.batches.output_keys(batch_id),
            ]
            uow.batches.delete(batch_id)
            details = {"batch_id": str(batch_id)} | ({"reason": reason} if reason else {})
            audit(ctx, uow, "BATCH_DELETED", actor=actor, **details)
            uow.commit()
        delete_stored(self._ctx.storage, [key for key in keys if key])

    def run_retention(self) -> int:
        """Delete everything past the retention period; returns how many batches went."""
        ctx = self._ctx
        cutoff = ctx.clock.now() - timedelta(days=ctx.retention_days)
        with ctx.uow() as uow:
            expired = uow.batches.expired(cutoff)
        deleted = 0
        for batch_id in expired:
            try:
                self.delete(batch_id, actor=ACTOR_SYSTEM, reason=REASON_RETENTION)
            except BatchNotFoundError:
                continue  # removed by someone else in the meantime
            deleted += 1
        return deleted
