"""The row store maps the template's extra slots into the render job (DD-40, contract item 7).

Test IDs: MS-DB-R1..R4 in docs/test-tree/multi-slot-model.md.
The template is stored through SqlTemplateRepository and the job is built through
SqlRowStore.preview_job, which uses the same mapping as a claimed row.
"""

from __future__ import annotations

import secrets
from uuid import UUID, uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.db.helpers import make_campaign
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.db.models import BatchRow
from vidgen.infrastructure.db.repositories import BatchRepository, NewRow, SqlTemplateRepository
from vidgen.infrastructure.db.row_store import SqlRowStore
from vidgen.ports.models import TemplateRecord
from vidgen.ports.rows import TemplateInfo


def make_cipher() -> AesGcmCipher:
    """A cipher with random keys for one test."""
    return AesGcmCipher(
        keys={"k1": secrets.token_bytes(32)},
        active_key_id="k1",
        index_key=secrets.token_bytes(32),
    )


def stored_job_template(
    db: Engine,
    *,
    primary: tuple[float, float] | None,
    extra_slots: tuple[tuple[float, float], ...],
) -> tuple[UUID, UUID]:
    """Store a template with the given slots and one batch row; returns (batch id, row id)."""
    cipher = make_cipher()
    template = TemplateRecord(
        id=uuid4(),
        video_key="templates/t.mp4",
        original_name="Krishan",
        duration_s=4.0,
        width=320,
        height=240,
        slot_start_s=None if primary is None else primary[0],
        slot_end_s=None if primary is None else primary[1],
        slot_source=None if primary is None else "MANUAL",
        slot_confirmed=primary is not None,
        extra_slots=extra_slots,
    )
    with Session(db) as session:
        campaign = make_campaign(session)
        SqlTemplateRepository(session).add(campaign.id, template)
        batch_id = BatchRepository(session, cipher).create_batch(campaign.id, template.id)
        BatchRepository(session, cipher).add_rows(batch_id, [NewRow(2, "Asha", "ID-1")])
        session.commit()
        row_id = session.execute(
            select(BatchRow.id).where(BatchRow.batch_id == batch_id)
        ).scalar_one()
    return batch_id, row_id


def job_template(db: Engine, batch_id: UUID, row_id: UUID) -> TemplateInfo:
    """The template snapshot of the render job the row store builds for the row."""
    store = SqlRowStore(sessionmaker(bind=db), make_cipher())
    job = store.preview_job(batch_id, row_id)
    assert job is not None
    return job.template


# ---- positive -------------------------------------------------------------------------


def test_extra_slots_reach_the_render_job_as_a_tuple_of_float_tuples(db: Engine) -> None:
    """MS-DB-R1: the stored extras come back exactly."""
    extras = ((2.2, 2.8), (3.1, 3.5))
    batch_id, row_id = stored_job_template(db, primary=(1.0, 2.0), extra_slots=extras)
    template = job_template(db, batch_id, row_id)
    assert template.extra_slots == extras
    assert all(isinstance(value, float) for pair in template.extra_slots for value in pair)


def test_job_slots_are_the_primary_and_extras_sorted_by_start(db: Engine) -> None:
    """MS-DB-R2: the render sees every slot in one sorted list."""
    batch_id, row_id = stored_job_template(
        db, primary=(2.0, 2.6), extra_slots=((3.1, 3.5), (0.0, 0.5))
    )
    template = job_template(db, batch_id, row_id)
    assert template.slots == ((0.0, 0.5), (2.0, 2.6), (3.1, 3.5))


def test_template_without_extras_gives_empty_extras_and_only_the_primary(db: Engine) -> None:
    """MS-DB-R3: the old single-slot case still works."""
    batch_id, row_id = stored_job_template(db, primary=(1.0, 2.0), extra_slots=())
    template = job_template(db, batch_id, row_id)
    assert template.extra_slots == ()
    assert template.slots == ((1.0, 2.0),)


# ---- negative -------------------------------------------------------------------------


def test_template_without_a_primary_slot_gives_no_slots_in_the_job(db: Engine) -> None:
    """MS-DB-R4: no primary slot means no slots, whatever is stored as extras."""
    batch_id, row_id = stored_job_template(db, primary=None, extra_slots=((2.2, 2.8),))
    template = job_template(db, batch_id, row_id)
    assert template.slots == ()
