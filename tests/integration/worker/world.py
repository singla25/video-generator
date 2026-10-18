"""Builds a database world (template, batch, encrypted rows) and a renderer with fakes."""

from __future__ import annotations

import io
import secrets
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from tests.fixtures.doubles import FakeClock, InMemoryStorage
from tests.fixtures.pipeline_fakes import (
    FakeEncoder,
    FakeLabels,
    FakeLipSync,
    FakeQuality,
    FakeVoice,
    PreviewEvents,
)
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.db.models import Batch, BatchRow, Campaign, Template
from vidgen.infrastructure.db.repositories import BatchRepository, NewRow
from vidgen.services.render_row import RenderConfig, RowRenderer

FOLDER = "2026-10-18-2"
TEMPLATE_KEY = "templates/t.mp4"
SLOT = (1.0, 1.6)  # a 0.6 s slot
PAUSE_S = 0.6
CREATOR = "Test Creator Org"
Person = tuple[str, str]  # (name, voter id)


@dataclass
class World:
    """Everything a worker test needs."""

    engine: Engine
    factory: sessionmaker[Session]
    cipher: AesGcmCipher
    storage: InMemoryStorage
    clock: FakeClock
    campaign_id: UUID
    template_id: UUID
    batch_id: UUID
    rows: dict[int, UUID]
    order: list[str]
    voice: FakeVoice
    encoder: FakeEncoder
    lipsync: FakeLipSync
    quality: FakeQuality
    labels: FakeLabels
    previews: PreviewEvents
    renderer: RowRenderer

    def row(self, number: int) -> dict[str, Any]:
        """Current database state of a row (no personal data columns)."""
        with Session(self.engine) as session:
            row = session.execute(
                select(BatchRow).where(
                    BatchRow.batch_id == self.batch_id, BatchRow.row_number == number
                )
            ).scalar_one()
            return {
                "id": row.id,
                "status": row.status,
                "attempts": row.attempts,
                "failure_code": row.failure_code,
                "output_key": row.output_key,
                "render_seconds": row.render_seconds,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
            }

    def statuses(self) -> dict[int, str]:
        """Status by row number."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(BatchRow.row_number, BatchRow.status).where(
                    BatchRow.batch_id == self.batch_id
                )
            )
            return {n: s for n, s in rows}

    def batch(self) -> dict[str, Any]:
        """Current batch state."""
        with Session(self.engine) as session:
            batch = session.get(Batch, self.batch_id)
            assert batch is not None
            return {
                "status": batch.status,
                "finished_at": batch.finished_at,
                "folder_name": batch.folder_name,
            }

    def set_batch(self, **values: Any) -> None:
        """Update batch columns."""
        with Session(self.engine) as session:
            session.execute(update(Batch).where(Batch.id == self.batch_id).values(**values))
            session.commit()

    def set_rows(self, numbers: Sequence[int], **values: Any) -> None:
        """Update row columns."""
        with Session(self.engine) as session:
            session.execute(
                update(BatchRow)
                .where(BatchRow.batch_id == self.batch_id, BatchRow.row_number.in_(numbers))
                .values(**values)
            )
            session.commit()

    def set_template(self, **values: Any) -> None:
        """Update template columns."""
        with Session(self.engine) as session:
            session.execute(
                update(Template).where(Template.id == self.template_id).values(**values)
            )
            session.commit()

    def expected_key(self, voter_id: str) -> str:
        """Where the output of a row is stored."""
        return f"{FOLDER}/{voter_id.replace('/', '_')}.mp4"


def build_world(
    engine: Engine,
    people: Sequence[Person] = (("Asha Verma", "A1"),),
    *,
    spoken: dict[int, str] | None = None,
    batch_status: str = "RUNNING",
    consent: bool = True,
    slot: tuple[float, float] | None = SLOT,
    config: RenderConfig | None = None,
    encoder: Any = None,
) -> World:
    """Create template, batch and rows, and a RowRenderer wired to fakes."""
    cipher = AesGcmCipher(
        keys={"k1": secrets.token_bytes(32)},
        active_key_id="k1",
        index_key=secrets.token_bytes(32),
    )
    storage = InMemoryStorage()
    storage.write(TEMPLATE_KEY, io.BytesIO(b"TEMPLATE-VIDEO"))
    clock = FakeClock(datetime(2026, 10, 18, 9, 0, tzinfo=UTC))
    factory = sessionmaker(engine, expire_on_commit=False)
    with Session(engine) as session:
        campaign = Campaign(name="default")
        session.add(campaign)
        session.flush()
        template = Template(
            campaign_id=campaign.id,
            video_key=TEMPLATE_KEY,
            original_name="Krishan",
            duration_s=4.0,
            width=320,
            height=240,
            slot_start_s=None if slot is None else slot[0],
            slot_end_s=None if slot is None else slot[1],
            slot_source="MANUAL",
            slot_confirmed=slot is not None,
            consent_confirmed=consent,
        )
        session.add(template)
        session.flush()
        repo = BatchRepository(session, cipher)
        batch_id = repo.create_batch(campaign.id, template.id)
        repo.add_rows(
            batch_id,
            [
                NewRow(n + 2, name, voter_id, spoken_name=(spoken or {}).get(n + 2))
                for n, (name, voter_id) in enumerate(people)
            ],
        )
        session.execute(
            update(Batch)
            .where(Batch.id == batch_id)
            .values(status=batch_status, folder_name=FOLDER, started_at=clock.now())
        )
        session.commit()
        rows = dict(
            session.execute(
                select(BatchRow.row_number, BatchRow.id).where(BatchRow.batch_id == batch_id)
            ).all()
        )
        campaign_id, template_id = campaign.id, template.id
    order: list[str] = []
    real_encoder = encoder
    voice, encoder = FakeVoice(order), FakeEncoder(order)
    lipsync, quality = FakeLipSync(order), FakeQuality(order)
    labels, previews = FakeLabels(), PreviewEvents()
    renderer = RowRenderer(
        session_factory=factory,
        storage=storage,
        cipher=cipher,
        voice=voice,
        lipsync=lipsync,
        encoder=real_encoder or encoder,
        quality=quality,
        labels=labels,
        clock=clock,
        config=config or RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S),
        preview_sink=previews,
    )
    return World(
        engine, factory, cipher, storage, clock, campaign_id, template_id, batch_id, rows,
        order, voice, encoder, lipsync, quality, labels, previews, renderer,
    )  # fmt: skip


def scratch_tempdir(monkeypatch: Any, tmp_path: Path) -> Path:
    """Point Python's temp directory at an empty folder so leftovers can be detected."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch
