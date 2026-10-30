"""SqlRowStore._spoken_name: the confirmed spelling wins for the preview row only (L4)."""

from __future__ import annotations

import logging
import secrets
import types
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.db.batch_documents import to_document
from vidgen.infrastructure.db.row_store import SqlRowStore
from vidgen.ports.batches import BatchRecord, PreviewRecord

CONFIRMED = "कृष्ण-Canary"
OWN = "अपना-Canary"
CIPHER = AesGcmCipher(
    keys={"k1": secrets.token_bytes(32)}, active_key_id="k1", index_key=secrets.token_bytes(32)
)


def store() -> SqlRowStore:
    """A store whose session factory is never used by ``_spoken_name``."""
    return SqlRowStore(None, CIPHER)  # type: ignore[arg-type]


def batch_with(preview_row: UUID | None, spoken: str | None) -> Any:
    """An ORM-like batch whose JSON document holds the given preview state."""
    record = BatchRecord(
        id=uuid4(),
        template_id=uuid4(),
        status="DRAFT",
        created_at=datetime(2026, 10, 28, tzinfo=UTC),
        sheet_key=None,
        sheet_name="s.csv",
        folder_name=None,
        idempotency_key=None,
        started_at=None,
        finished_at=None,
        mapping=None,
        preview=PreviewRecord(status="READY", row_id=preview_row, spoken_name=spoken),
    )
    return types.SimpleNamespace(
        id=record.id,
        template_id=record.template_id,
        status=record.status,
        created_at=record.created_at,
        sheet_key=None,
        folder_name=None,
        idempotency_key=None,
        started_at=None,
        finished_at=None,
        column_mapping=to_document(record, CIPHER),
    )


def row(row_id: UUID, own: str | None) -> Any:
    """An ORM-like row with an optional own (sheet) spoken name."""
    sealed = None if own is None else CIPHER.encrypt(own)
    return types.SimpleNamespace(id=row_id, spoken_name_enc=sealed)


def test_preview_row_gets_the_confirmed_name_over_its_own() -> None:
    rid = uuid4()
    assert store()._spoken_name(batch_with(rid, CONFIRMED), row(rid, OWN)) == CONFIRMED


def test_other_rows_keep_their_own_spoken_name() -> None:
    assert store()._spoken_name(batch_with(uuid4(), CONFIRMED), row(uuid4(), OWN)) == OWN


def test_other_rows_without_their_own_name_get_none() -> None:
    assert store()._spoken_name(batch_with(uuid4(), CONFIRMED), row(uuid4(), None)) is None


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_confirmation_falls_back_to_the_rows_own_name(blank: str | None) -> None:
    rid = uuid4()
    assert store()._spoken_name(batch_with(rid, blank), row(rid, OWN)) == OWN


def test_no_preview_row_and_no_own_name_is_none() -> None:
    rid = uuid4()
    assert store()._spoken_name(batch_with(None, None), row(rid, None)) is None


def test_hindi_confirmation_round_trips_through_encryption() -> None:
    rid = uuid4()
    batch = batch_with(rid, "कृष्ण कुमार")
    assert "कृष्ण" not in str(batch.column_mapping)
    assert store()._spoken_name(batch, row(rid, None)) == "कृष्ण कुमार"


def test_the_spoken_name_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    rid = uuid4()
    store()._spoken_name(batch_with(rid, CONFIRMED), row(rid, OWN))
    assert CONFIRMED not in caplog.text
    assert OWN not in caplog.text
