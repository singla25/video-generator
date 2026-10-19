"""The database itself rejects duplicate voter IDs in a batch (partial unique index).

Skipped rows are exempt: invalid and duplicate rows are stored as SKIPPED for the manifest.
"""

from __future__ import annotations

import secrets
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.integration.db.helpers import make_campaign, make_template
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.db.models import Batch, BatchRow
from vidgen.infrastructure.db.repositories import BatchRepository, NewRow


@pytest.fixture
def cipher() -> AesGcmCipher:
    """Cipher with random test keys."""
    return AesGcmCipher(
        keys={"k1": secrets.token_bytes(32)}, active_key_id="k1", index_key=secrets.token_bytes(32)
    )


def two_batches(session: Session) -> tuple[UUID, UUID, UUID]:
    """Campaign plus two empty batches on one template."""
    campaign = make_campaign(session)
    template = make_template(session, campaign)
    ids = []
    for _ in range(2):
        batch = Batch(campaign_id=campaign.id, template_id=template.id, status="DRAFT")
        session.add(batch)
        session.flush()
        ids.append(batch.id)
    return campaign.id, ids[0], ids[1]


def raw_row(campaign_id: UUID, batch_id: UUID, number: int, status: str, index: str) -> BatchRow:
    """A row built directly from the model, bypassing the repository."""
    return BatchRow(
        campaign_id=campaign_id,
        batch_id=batch_id,
        row_number=number,
        status=status,
        name_enc=b"n",
        voter_id_enc=b"v",
        voter_id_index=index,
        key_id="k1",
    )


# ---- rejected -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("QUEUED", "QUEUED"),
        ("QUEUED", "COMPLETED"),
        ("FAILED", "QUEUED"),
        ("CANCELLED", "PROCESSING"),
    ],
)
def test_two_non_skipped_rows_with_the_same_index_are_rejected_by_the_database(
    db: Engine, first: str, second: str
) -> None:
    """Raw model insert: the constraint lives in the database, not in application code."""
    with Session(db) as session:
        campaign_id, batch_id, _ = two_batches(session)
        session.add(raw_row(campaign_id, batch_id, 2, first, "same-index"))
        session.add(raw_row(campaign_id, batch_id, 3, second, "same-index"))
        with pytest.raises(IntegrityError):
            session.flush()


def test_the_repository_cannot_store_two_live_rows_with_equivalent_ids(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """Equivalent IDs (A2: trim, casefold, sanitise) share a blind index, so they collide."""
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        repo = BatchRepository(session, cipher)
        batch_id = repo.create_batch(campaign.id, template.id)
        with pytest.raises(IntegrityError):
            repo.add_rows(
                batch_id,
                [NewRow(2, "Asha", "RJ/12/097"), NewRow(3, "Bina", " rj_12_097 ")],
            )
            session.flush()


def test_a_second_live_row_added_later_is_rejected_too(db: Engine, cipher: AesGcmCipher) -> None:
    """The guard also holds across separate inserts."""
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        repo = BatchRepository(session, cipher)
        batch_id = repo.create_batch(campaign.id, template.id)
        repo.add_rows(batch_id, [NewRow(2, "Asha", "A1")])
        session.commit()
        with pytest.raises(IntegrityError):
            repo.add_rows(batch_id, [NewRow(3, "Bina", "A1")])
            session.commit()


# ---- allowed --------------------------------------------------------------------------


def test_a_skipped_duplicate_next_to_a_live_row_is_allowed(db: Engine) -> None:
    """The invalid/duplicate row is kept as SKIPPED for the manifest."""
    with Session(db) as session:
        campaign_id, batch_id, _ = two_batches(session)
        session.add(raw_row(campaign_id, batch_id, 2, "QUEUED", "dup"))
        session.add(raw_row(campaign_id, batch_id, 3, "SKIPPED", "dup"))
        session.commit()
        assert session.query(BatchRow).count() == 2


def test_skipped_row_inserted_before_the_live_row_is_allowed(db: Engine) -> None:
    """Order does not matter."""
    with Session(db) as session:
        campaign_id, batch_id, _ = two_batches(session)
        session.add(raw_row(campaign_id, batch_id, 2, "SKIPPED", "dup"))
        session.add(raw_row(campaign_id, batch_id, 3, "QUEUED", "dup"))
        session.commit()
        assert session.query(BatchRow).count() == 2


def test_many_skipped_duplicates_are_allowed(db: Engine) -> None:
    """Three rows, one ID: rows 3 and 4 are SKIPPED duplicates of row 2."""
    with Session(db) as session:
        campaign_id, batch_id, _ = two_batches(session)
        session.add(raw_row(campaign_id, batch_id, 2, "COMPLETED", "dup"))
        session.add(raw_row(campaign_id, batch_id, 3, "SKIPPED", "dup"))
        session.add(raw_row(campaign_id, batch_id, 4, "SKIPPED", "dup"))
        session.commit()
        assert session.query(BatchRow).count() == 3


def test_the_same_index_in_another_batch_is_allowed(db: Engine) -> None:
    """The guard is per batch."""
    with Session(db) as session:
        campaign_id, first, second = two_batches(session)
        session.add(raw_row(campaign_id, first, 2, "QUEUED", "same"))
        session.add(raw_row(campaign_id, second, 2, "QUEUED", "same"))
        session.commit()
        assert session.query(BatchRow).count() == 2


def test_a_failed_row_can_be_requeued_without_hitting_the_guard(db: Engine) -> None:
    """Status changes (retry) never create a second row, so updating stays legal."""
    with Session(db) as session:
        campaign_id, batch_id, _ = two_batches(session)
        row = raw_row(campaign_id, batch_id, 2, "FAILED", "x")
        session.add(row)
        session.commit()
        row.status = "QUEUED"
        session.commit()
        assert session.query(BatchRow).one().status == "QUEUED"
