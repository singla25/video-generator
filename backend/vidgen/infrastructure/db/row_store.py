"""Row claiming and completion on Postgres (T14).

``claim`` takes the row lock with ``FOR UPDATE SKIP LOCKED``: a second worker that gets the
same message in the same instant is told the row is busy instead of waiting or rendering it
twice. ``finish`` locks the batch row, so only one worker can complete a batch.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from vidgen.domain.outcomes import RowOutcomeKind
from vidgen.infrastructure.db.batch_store import SqlBatchStore
from vidgen.infrastructure.db.models import Batch, BatchRow, Template
from vidgen.ports.rows import (
    ClaimAction,
    ClaimDecision,
    ClaimResult,
    ClaimSnapshot,
    Completion,
    ManifestInput,
    RowJob,
    RowUpdate,
    TemplateInfo,
)

if TYPE_CHECKING:
    from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher

PENDING_STATUSES = ("QUEUED", "PROCESSING")
TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED"})


class SqlRowStore:
    """``RowStore`` on Postgres."""

    def __init__(self, factory: sessionmaker[Session], cipher: AesGcmCipher) -> None:
        self._factory = factory
        self._cipher = cipher

    def claim(
        self,
        batch_id: UUID,
        row_id: UUID,
        decide: Callable[[ClaimSnapshot], ClaimDecision],
        now: datetime,
    ) -> ClaimResult:
        """Lock the row, apply the decision and return a job when the row was claimed."""
        with self._factory() as session:
            row = self._locked_row(session, batch_id, row_id)
            if isinstance(row, RowOutcomeKind):
                return ClaimResult(row, None)
            batch = session.get(Batch, batch_id)
            assert batch is not None  # noqa: S101 - the row's foreign key guarantees it
            decision = decide(ClaimSnapshot(batch.status, row.status, row.started_at))
            if decision.action is ClaimAction.CANCEL_ROW:
                row.status, row.finished_at = "CANCELLED", now
            if decision.action is not ClaimAction.CLAIM:
                session.commit()
                return ClaimResult(decision.outcome, None)
            row.status, row.started_at, row.finished_at = "PROCESSING", now, None
            row.attempts += 1
            job = self._job(session, batch, row)
            session.commit()
            return ClaimResult(RowOutcomeKind.COMPLETED, job)

    def preview_job(self, batch_id: UUID, row_id: UUID) -> RowJob | None:
        """The row as a job for a preview; nothing is changed."""
        with self._factory() as session:
            row = session.execute(
                select(BatchRow).where(BatchRow.id == row_id, BatchRow.batch_id == batch_id)
            ).scalar_one_or_none()
            batch = session.get(Batch, batch_id)
            if row is None or batch is None:
                return None
            return self._job(session, batch, row)

    def finish(
        self,
        batch_id: UUID,
        row_id: UUID,
        update: RowUpdate,
        now: datetime,
        decide_completion: Callable[[str, int], Completion],
    ) -> ManifestInput | None:
        """Store the row's new state; complete the batch when nothing is pending."""
        with self._factory() as session:
            batch = session.execute(
                select(Batch).where(Batch.id == batch_id).with_for_update()
            ).scalar_one_or_none()
            row = session.get(BatchRow, row_id)
            if batch is None or row is None:
                return None  # the batch was deleted while the row was rendering
            row.status = update.status
            row.failure_code = update.failure_code
            row.output_key = update.output_key
            row.render_seconds = update.render_seconds
            row.finished_at = now if update.status in TERMINAL_STATUSES else None
            session.flush()
            manifest = None
            if update.status in TERMINAL_STATUSES:
                manifest = self._complete(session, batch, now, decide_completion)
            session.commit()
            return manifest

    # ---- helpers -----------------------------------------------------------------------

    @staticmethod
    def _locked_row(session: Session, batch_id: UUID, row_id: UUID) -> BatchRow | RowOutcomeKind:
        """The locked row, NOOP if it does not exist, BUSY if another worker holds its lock."""
        where = (BatchRow.id == row_id, BatchRow.batch_id == batch_id)
        locked = session.execute(
            select(BatchRow).where(*where).with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if locked is not None:
            return locked
        exists = session.execute(select(BatchRow.id).where(*where)).first()
        return RowOutcomeKind.BUSY if exists else RowOutcomeKind.NOOP

    def _job(self, session: Session, batch: Batch, row: BatchRow) -> RowJob:
        template = session.get(Template, batch.template_id)
        assert template is not None  # noqa: S101 - the batch's foreign key guarantees it
        start, end = template.slot_start_s, template.slot_end_s
        spoken = row.spoken_name_enc
        return RowJob(
            batch_id=batch.id,
            row_id=row.id,
            row_number=row.row_number,
            name=self._cipher.decrypt(bytes(row.name_enc)),
            spoken_name=None if spoken is None else self._cipher.decrypt(bytes(spoken)),
            voter_id=self._cipher.decrypt(bytes(row.voter_id_enc)),
            attempts=row.attempts,
            folder_name=batch.folder_name or "",
            template=TemplateInfo(
                video_key=template.video_key,
                width=template.width,
                height=template.height,
                slot=None if start is None or end is None else (start, end),
                slot_confirmed=template.slot_confirmed,
                consent_confirmed=template.consent_confirmed,
            ),
        )

    def _complete(
        self,
        session: Session,
        batch: Batch,
        now: datetime,
        decide_completion: Callable[[str, int], Completion],
    ) -> ManifestInput | None:
        pending = session.execute(
            select(func.count())
            .select_from(BatchRow)
            .where(BatchRow.batch_id == batch.id, BatchRow.status.in_(PENDING_STATUSES))
        ).scalar_one()
        decision = decide_completion(batch.status, int(pending))
        if decision.new_status is not None:
            batch.status, batch.finished_at = decision.new_status, now
        if not decision.write_manifest:
            return None
        rows = list(SqlBatchStore(session, self._cipher).iter_rows(batch.id))
        return ManifestInput(batch.folder_name or "", rows)
