"""BL-11: SqlRowStore.rows_missing_spoken_name / set_spoken_name on the throwaway database.

Contract: docs/test-tree/bl11-spellings-for-all-rows.md (ids SP-DB-*).
"""

from __future__ import annotations

import secrets
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.db.helpers import make_campaign, make_template
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.db.models import BatchRow
from vidgen.infrastructure.db.repositories import BatchRepository, NewRow
from vidgen.infrastructure.db.row_store import SqlRowStore

SPELLING = "आशा-वर्मा"


@pytest.fixture
def cipher() -> AesGcmCipher:
    return AesGcmCipher(
        keys={"k1": secrets.token_bytes(32)},
        active_key_id="k1",
        index_key=secrets.token_bytes(32),
    )


def seed(
    db: Engine, cipher: AesGcmCipher, rows: list[NewRow]
) -> tuple[UUID, dict[int, UUID], SqlRowStore]:
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        repo = BatchRepository(session, cipher)
        batch_id = repo.create_batch(campaign.id, template.id)
        repo.add_rows(batch_id, rows)
        session.commit()
        ids = dict(
            session.execute(
                select(BatchRow.row_number, BatchRow.id).where(BatchRow.batch_id == batch_id)
            ).all()
        )
    return batch_id, ids, SqlRowStore(sessionmaker(bind=db), cipher)


def raw_spoken(db: Engine, row_id: UUID) -> bytes | None:
    with Session(db) as session:
        value = session.execute(
            select(BatchRow.spoken_name_enc).where(BatchRow.id == row_id)
        ).scalar_one()
        return None if value is None else bytes(value)


def test_missing_rows_come_back_with_decrypted_names_in_row_order(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """SP-DB-P1."""
    batch, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1"), NewRow(3, "Zoë", "A2")])
    page = store.rows_missing_spoken_name(batch, 0, 10)
    assert [(m.row_number, m.name, m.row_id) for m in page] == [
        (2, "Asha", ids[2]),
        (3, "Zoë", ids[3]),
    ]


def test_the_spelling_is_stored_encrypted_and_decrypts_back(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """SP-DB-P2: the plaintext is nowhere in the raw column."""
    _, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1")])
    assert store.set_spoken_name(ids[2], SPELLING) is True
    raw = raw_spoken(db, ids[2])
    assert raw is not None
    assert SPELLING.encode() not in raw
    assert "आशा".encode() not in raw
    assert cipher.decrypt(raw) == SPELLING


def test_a_stored_spelling_removes_the_row_from_the_missing_list(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """SP-DB-P3."""
    batch, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1")])
    store.set_spoken_name(ids[2], SPELLING)
    assert store.rows_missing_spoken_name(batch, 0, 10) == []


def test_the_cursor_and_limit_page_through_the_rows(db: Engine, cipher: AesGcmCipher) -> None:
    """SP-DB-P4."""
    rows = [NewRow(n, f"Name{n}", f"V{n}") for n in range(2, 9)]
    batch, _, store = seed(db, cipher, rows)
    first = store.rows_missing_spoken_name(batch, 0, 3)
    second = store.rows_missing_spoken_name(batch, first[-1].row_number, 3)
    third = store.rows_missing_spoken_name(batch, second[-1].row_number, 3)
    assert [m.row_number for m in first + second + third] == list(range(2, 9))
    assert store.rows_missing_spoken_name(batch, 8, 3) == []


def test_set_does_not_overwrite_an_existing_spelling(db: Engine, cipher: AesGcmCipher) -> None:
    """SP-DB-N1: compare-and-set."""
    _, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1", spoken_name="पहला")])
    before = raw_spoken(db, ids[2])
    assert store.set_spoken_name(ids[2], SPELLING) is False
    assert raw_spoken(db, ids[2]) == before


def test_rows_with_a_sheet_spoken_name_are_not_listed(db: Engine, cipher: AesGcmCipher) -> None:
    """SP-DB-N2."""
    batch, _, store = seed(
        db, cipher, [NewRow(2, "Asha", "A1", spoken_name="आशा"), NewRow(3, "Bina", "A2")]
    )
    assert [m.name for m in store.rows_missing_spoken_name(batch, 0, 10)] == ["Bina"]


@pytest.mark.parametrize("status", ["PROCESSING", "COMPLETED", "FAILED", "SKIPPED", "CANCELLED"])
def test_rows_that_are_not_queued_are_not_listed_and_not_written(
    db: Engine, cipher: AesGcmCipher, status: str
) -> None:
    """SP-DB-N3."""
    batch, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1", status=status)])
    assert store.rows_missing_spoken_name(batch, 0, 10) == []
    assert store.set_spoken_name(ids[2], SPELLING) is False
    assert raw_spoken(db, ids[2]) is None


def test_a_row_claimed_between_read_and_write_is_not_changed(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """SP-DB-N4: concurrency with a row claim."""
    batch, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1")])
    assert store.rows_missing_spoken_name(batch, 0, 10)
    with Session(db) as session:
        session.execute(update(BatchRow).where(BatchRow.id == ids[2]).values(status="PROCESSING"))
        session.commit()
    assert store.set_spoken_name(ids[2], SPELLING) is False
    assert raw_spoken(db, ids[2]) is None


def test_a_deleted_batch_lists_nothing_and_writes_nothing(db: Engine, cipher: AesGcmCipher) -> None:
    """SP-DB-N5."""
    batch, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1")])
    with Session(db) as session:
        BatchRepository(session, cipher).delete_batch(batch)
        session.commit()
    assert store.rows_missing_spoken_name(batch, 0, 10) == []
    assert store.set_spoken_name(ids[2], SPELLING) is False
    assert store.set_spoken_name(uuid4(), SPELLING) is False


def test_another_batch_is_not_listed(db: Engine, cipher: AesGcmCipher) -> None:
    """SP-DB-N6."""
    batch, _, store = seed(db, cipher, [NewRow(2, "Asha", "A1")])
    assert store.rows_missing_spoken_name(uuid4(), 0, 10) == []
    assert len(store.rows_missing_spoken_name(batch, 0, 10)) == 1


@pytest.mark.parametrize("name", ["Zoë O'Brien-Smith", "كريم", "😀 Kabir", "x" * 200])
def test_unicode_and_long_names_round_trip(db: Engine, cipher: AesGcmCipher, name: str) -> None:
    """SP-DB-E1."""
    batch, ids, store = seed(db, cipher, [NewRow(2, name, "A1")])
    assert store.rows_missing_spoken_name(batch, 0, 10)[0].name == name
    assert store.set_spoken_name(ids[2], name[::-1]) is True
    assert cipher.decrypt(raw_spoken(db, ids[2]) or b"") == name[::-1]


def test_set_twice_keeps_the_first_value(db: Engine, cipher: AesGcmCipher) -> None:
    """SP-DB-E2."""
    _, ids, store = seed(db, cipher, [NewRow(2, "Asha", "A1")])
    assert store.set_spoken_name(ids[2], "पहला") is True
    first = raw_spoken(db, ids[2])
    assert store.set_spoken_name(ids[2], "दूसरा") is False
    assert raw_spoken(db, ids[2]) == first
