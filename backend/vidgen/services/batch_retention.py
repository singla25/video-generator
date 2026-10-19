"""Batch deletion and the retention job (AC17, A8, B12, C5)."""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from vidgen.domain.codes import DomainError
from vidgen.services.audit import ACTOR_ADMIN, ACTOR_SYSTEM
from vidgen.services.batch_support import BatchContext, audit
from vidgen.services.errors import BatchNotFoundError

logger = logging.getLogger(__name__)
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
        self._delete_files([key for key in keys if key])

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

    def _delete_files(self, keys: list[str]) -> None:
        """Best effort: one stuck file must not stop the rest from being removed."""
        failed = 0
        for key in keys:
            try:
                self._ctx.storage.delete(key)
            except (OSError, DomainError):
                failed += 1
        if failed:
            logger.error("some batch files could not be deleted", extra={"failed_files": failed})
