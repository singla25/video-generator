"""Repositories: encrypted rows, blind-index lookup, cascade delete, audit (ADR-005, AC17, C4)."""

from __future__ import annotations

import secrets
import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from tests.integration.db.helpers import make_campaign, make_template
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher, DecryptionError
from vidgen.infrastructure.db.repositories import (
    AuditRepository,
    BatchRepository,
    NewRow,
    ensure_default_campaign,
)

DEV_NAME = "\u0930\u093e\u091c\u0947\u0936 \u0915\u0941\u092e\u093e\u0930"
ID_CANARY_2 = "ZQ-CANARY-ID-7731"  # long on purpose: a short needle can match random ciphertext


def make_cipher(key_id: str = "k1", key: bytes | None = None) -> AesGcmCipher:
    """A cipher with random test keys."""
    return AesGcmCipher(
        keys={key_id: key or secrets.token_bytes(32)},
        active_key_id=key_id,
        index_key=secrets.token_bytes(32),
    )


@pytest.fixture
def cipher() -> AesGcmCipher:
    """Cipher shared by one test."""
    return make_cipher()


def new_batch(db: Engine, cipher: AesGcmCipher, rows: list[NewRow]) -> tuple[UUID, UUID]:
    """Create campaign, template, batch and rows; return (campaign_id, batch_id)."""
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        repo = BatchRepository(session, cipher)
        batch_id = repo.create_batch(campaign.id, template.id)
        repo.add_rows(batch_id, rows)
        session.commit()
        return campaign.id, batch_id


# ---- round trip and lookup ------------------------------------------------------------


def test_rows_round_trip_with_latin_and_devanagari_text(db: Engine, cipher: AesGcmCipher) -> None:
    """TT-AC17-P1 (storage side)."""
    rows = [
        NewRow(2, "Rajesh Kumar", "RJ/12/097/183866", spoken_name="Rajesh Kumar Ji"),
        NewRow(3, DEV_NAME, "A2"),
    ]
    _, batch_id = new_batch(db, cipher, rows)
    with Session(db) as session:
        stored = BatchRepository(session, cipher).rows(batch_id)
    assert [(r.row_number, r.name, r.voter_id, r.spoken_name) for r in stored] == [
        (2, "Rajesh Kumar", "RJ/12/097/183866", "Rajesh Kumar Ji"),
        (3, DEV_NAME, "A2", None),
    ]


def test_row_status_is_stored_in_plain_text_for_counting(db: Engine, cipher: AesGcmCipher) -> None:
    """AC14: counts need no decryption."""
    _, batch_id = new_batch(
        db, cipher, [NewRow(2, "A", "1", status="QUEUED"), NewRow(3, "B", "2", status="SKIPPED")]
    )
    with Session(db) as session:
        stored = BatchRepository(session, cipher).rows(batch_id)
    assert [r.status for r in stored] == ["QUEUED", "SKIPPED"]


def test_rows_are_returned_in_sheet_order(db: Engine, cipher: AesGcmCipher) -> None:
    """AC14-P4: stable order."""
    rows = [NewRow(n, f"Name {n}", f"ID{n}") for n in (7, 3, 5, 2)]
    _, batch_id = new_batch(db, cipher, rows)
    with Session(db) as session:
        numbers = [r.row_number for r in BatchRepository(session, cipher).rows(batch_id)]
    assert numbers == [2, 3, 5, 7]


def test_find_by_voter_id_uses_the_blind_index_with_id_normalisation(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """AC14-P7 / AC17-E4: lookup by ID without decrypting every row."""
    _, batch_id = new_batch(db, cipher, [NewRow(2, "Asha", "RJ/12/097"), NewRow(3, "Bina", "B2")])
    with Session(db) as session:
        repo = BatchRepository(session, cipher)
        found = repo.find_by_voter_id(batch_id, " rj_12_097 ")
        assert found is not None
        assert found.name == "Asha"
        assert repo.find_by_voter_id(batch_id, "nope") is None


def test_find_by_voter_id_never_crosses_batches(db: Engine, cipher: AesGcmCipher) -> None:
    """AC14-N3: search is scoped to one batch."""
    _, first = new_batch(db, cipher, [NewRow(2, "Asha", "SAME")])
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        repo = BatchRepository(session, cipher)
        second = repo.create_batch(campaign.id, template.id)
        repo.add_rows(second, [NewRow(2, "Other", "SAME")])
        session.commit()
        found = repo.find_by_voter_id(first, "SAME")
        assert found is not None
        assert found.name == "Asha"


def test_key_id_is_stored_with_each_row(db: Engine, cipher: AesGcmCipher) -> None:
    """ADR-005: key id per value for rotation."""
    _, batch_id = new_batch(db, cipher, [NewRow(2, "Asha", "A1")])
    with Session(db) as session:
        stored = BatchRepository(session, cipher).rows(batch_id)
        raw = session.execute(text("SELECT key_id, name_enc FROM batch_rows")).one()
    assert stored[0].key_id == "k1"
    assert raw.key_id == "k1"
    assert cipher.key_id_of(bytes(raw.name_enc)) == "k1"


def test_rows_written_before_a_key_rotation_still_read(db: Engine) -> None:
    """ADR-005 / AC17-E2."""
    old_key = secrets.token_bytes(32)
    index_key = secrets.token_bytes(32)
    old = AesGcmCipher(keys={"k1": old_key}, active_key_id="k1", index_key=index_key)
    _, batch_id = new_batch(db, old, [NewRow(2, "Asha", "A1")])
    rotated = AesGcmCipher(
        keys={"k1": old_key, "k2": secrets.token_bytes(32)}, active_key_id="k2", index_key=index_key
    )
    with Session(db) as session:
        repo = BatchRepository(session, rotated)
        assert repo.rows(batch_id)[0].name == "Asha"
        repo.add_rows(batch_id, [NewRow(3, "Bina", "B2")])
        session.commit()
        keys = [r.key_id for r in repo.rows(batch_id)]
    assert keys == ["k1", "k2"]


def test_wrong_key_cannot_read_rows(db: Engine, cipher: AesGcmCipher) -> None:
    """AC17-N1."""
    _, batch_id = new_batch(db, cipher, [NewRow(2, "Asha", "A1")])
    with Session(db) as session, pytest.raises(DecryptionError):
        BatchRepository(session, make_cipher()).rows(batch_id)


# ---- encryption at rest ---------------------------------------------------------------


def test_raw_table_contents_hold_no_plaintext_names_or_ids(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """TT-AC17-P2 (C5): query the raw table and look for the canaries as bytes and as text."""
    new_batch(
        db,
        cipher,
        [
            NewRow(2, CANARY_NAME, CANARY_ID, spoken_name=CANARY_NAME + " Ji"),
            NewRow(3, DEV_NAME, ID_CANARY_2),
        ],
    )
    with db.connect() as conn:
        as_text = conn.execute(text("SELECT t::text FROM batch_rows t")).scalars().all()
        binary = conn.execute(
            text("SELECT name_enc, spoken_name_enc, voter_id_enc FROM batch_rows")
        ).all()
    haystack = "\n".join(as_text)
    for secret in (CANARY_NAME, CANARY_ID, DEV_NAME, ID_CANARY_2):
        assert secret not in haystack
        assert secret.encode("utf-8") not in haystack.encode("utf-8")
        for row in binary:
            for blob in row:
                if blob is not None:
                    assert secret.encode("utf-8") not in bytes(blob)


def test_the_blind_index_column_is_keyed_and_not_the_plain_id(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """TT-AC17-P3."""
    new_batch(db, cipher, [NewRow(2, "Asha", "183866")])
    with db.connect() as conn:
        index = conn.execute(text("SELECT voter_id_index FROM batch_rows")).scalar_one()
    assert index == cipher.blind_index("183866")
    assert "183866" not in index


# ---- delete and concurrency -----------------------------------------------------------


def test_delete_batch_removes_its_rows_but_not_other_batches(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """TT-AC17-P5 (database side)."""
    _, first = new_batch(db, cipher, [NewRow(2, "A", "1"), NewRow(3, "B", "2")])
    _, second = new_batch(db, cipher, [NewRow(2, "C", "3")])
    with Session(db) as session:
        BatchRepository(session, cipher).delete_batch(first)
        session.commit()
    with Session(db) as session:
        repo = BatchRepository(session, cipher)
        assert repo.rows(first) == []
        assert len(repo.rows(second)) == 1
        assert session.execute(text("SELECT count(*) FROM batches")).scalar_one() == 1


def test_delete_of_an_unknown_batch_is_harmless(db: Engine, cipher: AesGcmCipher) -> None:
    """TT-AC17-N5 (repository level)."""
    with Session(db) as session:
        BatchRepository(session, cipher).delete_batch(UUID(int=0))
        session.commit()


def test_two_sessions_updating_different_rows_do_not_block(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """TT-AC12-E4 (smoke): row-level locks only; the second update is not blocked."""
    _, batch_id = new_batch(db, cipher, [NewRow(2, "A", "1"), NewRow(3, "B", "2")])
    first = Session(db)
    second = Session(db)
    try:
        first.execute(text("UPDATE batch_rows SET status = 'PROCESSING' WHERE row_number = 2"))
        second.execute(text("SET LOCAL lock_timeout = '2s'"))
        second.execute(text("UPDATE batch_rows SET status = 'PROCESSING' WHERE row_number = 3"))
        second.commit()
        first.commit()
    except OperationalError as exc:  # pragma: no cover - failure path
        pytest.fail(f"second session was blocked: {exc}")
    finally:
        first.close()
        second.close()
    with Session(db) as session:
        statuses = [r.status for r in BatchRepository(session, cipher).rows(batch_id)]
    assert statuses == ["PROCESSING", "PROCESSING"]


def test_concurrent_writers_on_separate_connections_all_succeed(
    db: Engine, cipher: AesGcmCipher
) -> None:
    """TT-AC12-E4 (smoke): four threads add rows to one batch."""
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        batch_id = BatchRepository(session, cipher).create_batch(campaign.id, template.id)
        session.commit()
    errors: list[Exception] = []

    def add(n: int) -> None:
        try:
            with Session(db) as session:
                BatchRepository(session, cipher).add_rows(batch_id, [NewRow(n, f"N{n}", f"I{n}")])
                session.commit()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=add, args=(n,)) for n in range(2, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with Session(db) as session:
        assert len(BatchRepository(session, cipher).rows(batch_id)) == 4


# ---- audit ----------------------------------------------------------------------------


def test_audit_entries_round_trip_in_order_with_filtering(db: Engine) -> None:
    """C4."""
    start = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    with Session(db) as session:
        campaign_id = ensure_default_campaign(session)
        audit = AuditRepository(session)
        audit.add(
            campaign_id=campaign_id, actor="admin", action="LOGIN_SUCCEEDED", at=start, details={}
        )
        audit.add(
            campaign_id=campaign_id,
            actor="admin",
            action="TEMPLATE_UPLOADED",
            at=start + timedelta(minutes=1),
            details={"template_id": "t1", "size_bytes": 12},
        )
        session.commit()
        everything = audit.list(campaign_id=campaign_id)
        uploads = audit.list(campaign_id=campaign_id, action="TEMPLATE_UPLOADED")
    assert [e.action for e in everything] == ["LOGIN_SUCCEEDED", "TEMPLATE_UPLOADED"]
    assert uploads[0].details == {"template_id": "t1", "size_bytes": 12}
    assert uploads[0].actor == "admin"
    assert uploads[0].at == start + timedelta(minutes=1)


def test_audit_repository_offers_no_update_or_delete(db: Engine) -> None:
    """C4: append-only at the repository level."""
    with Session(db) as session:
        audit = AuditRepository(session)
        for name in ("update", "delete", "remove", "clear", "edit"):
            assert not hasattr(audit, name)


def test_ensure_default_campaign_is_idempotent(db: Engine) -> None:
    """D6: one default campaign, created on first use."""
    with Session(db) as session:
        first = ensure_default_campaign(session)
        session.commit()
        second = ensure_default_campaign(session)
        session.commit()
        assert first == second
        assert session.execute(text("SELECT count(*) FROM campaigns")).scalar_one() == 1
