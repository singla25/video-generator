"""POST /batches/{id}/rows/{row_number}/retry: re-queue one failed row (DD-18, R7.4).

Contract: row FAILED -> QUEUED, failure_code cleared, attempts kept, one job enqueued, a COMPLETED
batch becomes RUNNING, response is the batch JSON. Anything else is refused without side effects.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import pytest
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from tests.integration.api.batch_helpers import (
    get_batch,
    new_batch,
    people,
    post_action,
    row_ids,
    row_status,
    running_batch,
    set_batch,
    set_rows,
)
from tests.integration.api.conftest import Env
from tests.integration.api.helpers import audit_actions
from vidgen.infrastructure.db.models import BatchRow

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def retry(
    env: Env, batch_id: str, row: int | str, *, headers: dict[str, str] | None = None
) -> Response:
    """POST the per-row retry with the CSRF header unless ``headers`` is given."""
    return env.client.post(
        f"/batches/{batch_id}/rows/{row}/retry", headers=env.csrf if headers is None else headers
    )


def attempts_of(db: Engine, batch_id: str, number: int) -> int:
    """The stored attempt counter of one row."""
    with Session(db) as session:
        value = session.execute(
            select(BatchRow.attempts).where(
                BatchRow.batch_id == UUID(batch_id), BatchRow.row_number == number
            )
        ).scalar_one()
        return int(value)


@pytest.fixture
def failed(env: Env, db: Engine) -> str:
    """A running batch of 4 rows: row 3 FAILED (2 attempts), row 4 COMPLETED, others queued."""
    batch_id = running_batch(env, people(4))
    set_rows(db, batch_id, [3], status="FAILED", failure_code="TTS_FAILED", attempts=2)
    set_rows(db, batch_id, [4], status="COMPLETED")
    env.queue.rows.clear()
    return batch_id


def test_retry_requeues_exactly_that_row(env: Env, db: Engine, failed: str) -> None:
    """Row 3 goes QUEUED; its neighbours are untouched; one job is enqueued for it."""
    set_rows(db, failed, [2], status="FAILED", failure_code="STORAGE_ERROR")
    response = retry(env, failed, 3)
    assert response.status_code == 200, response.text
    statuses = row_status(db, failed)
    assert (statuses[2], statuses[3], statuses[4]) == ("FAILED", "QUEUED", "COMPLETED")
    assert env.queue.rows == [(UUID(failed), row_ids(db, failed)[3])]


def test_retry_clears_failure_code_but_keeps_attempt_history(
    env: Env, db: Engine, failed: str
) -> None:
    """The rows list shows a fresh state; the attempts counter is not reset."""
    assert retry(env, failed, 3).status_code == 200
    rows = env.client.get(f"/batches/{failed}/rows").json()["rows"]
    row = next(r for r in rows if r["row_number"] == 3)
    assert (row["status"], row["failure_code"], row["message"]) == ("QUEUED", None, None)
    assert attempts_of(db, failed, 3) == 2


def test_retry_returns_the_batch(env: Env, failed: str) -> None:
    """Same JSON shape as the other batch actions."""
    body: dict[str, Any] = retry(env, failed, 3).json()
    assert body["id"] == failed
    assert body["counts"]["queued"] >= 1


def test_retry_on_a_completed_batch_makes_it_running_again(env: Env, db: Engine) -> None:
    """COMPLETED -> RUNNING when a row is re-queued."""
    batch_id = running_batch(env, people(2))
    set_rows(db, batch_id, [2], status="COMPLETED")
    set_rows(db, batch_id, [3], status="FAILED", failure_code="RENDER_TIMEOUT")
    set_batch(db, batch_id, status="COMPLETED")
    assert get_batch(env, batch_id)["status"] == "COMPLETED"
    assert retry(env, batch_id, 3).status_code == 200
    assert get_batch(env, batch_id)["status"] == "RUNNING"


@pytest.mark.parametrize("status", ["QUEUED", "PROCESSING", "COMPLETED", "SKIPPED", "CANCELLED"])
def test_non_failed_row_is_409_invalid_state_with_no_side_effects(
    env: Env, db: Engine, failed: str, status: str
) -> None:
    """Only FAILED rows can be retried."""
    set_rows(db, failed, [2], status=status)
    response = retry(env, failed, 2)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"
    assert row_status(db, failed)[2] == status
    assert env.queue.rows == []


@pytest.mark.parametrize("row", [999, 1, 0, -1])
def test_unknown_row_is_404(env: Env, failed: str, row: int) -> None:
    """Row numbers outside the sheet (row 1 is the header)."""
    response = retry(env, failed, row)
    assert response.status_code in (404, 422)
    if row in (999, 1):
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
    assert env.queue.rows == []


def test_non_numeric_row_is_a_validation_error(env: Env, failed: str) -> None:
    """Path parameter must be an integer."""
    response = retry(env, failed, "abc")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_batch_is_404(env: Env) -> None:
    """No such batch."""
    response = retry(env, UNKNOWN_ID, 2)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_row_of_another_batch_is_not_reachable(env: Env, db: Engine, failed: str) -> None:
    """A failed row in batch A cannot be retried through batch B."""
    other = new_batch(env, people(1))
    assert retry(env, other, 3).status_code == 404
    assert row_status(db, failed)[3] == "FAILED"


def test_cancelled_batch_refuses_with_409(env: Env, db: Engine, failed: str) -> None:
    """After cancel nothing may be re-queued."""
    assert post_action(env, failed, "cancel").status_code == 200
    set_rows(db, failed, [3], status="FAILED", failure_code="TTS_FAILED")
    env.queue.rows.clear()
    response = retry(env, failed, 3)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"
    assert row_status(db, failed)[3] == "FAILED"
    assert env.queue.rows == []


def test_second_quick_call_is_409_and_enqueues_nothing_more(env: Env, failed: str) -> None:
    """Idempotent in effect: the row is already QUEUED, so a repeat is refused."""
    assert retry(env, failed, 3).status_code == 200
    again = retry(env, failed, 3)
    assert again.status_code == 409
    assert again.json()["code"] == "INVALID_STATE"
    assert len(env.queue.rows) == 1


def test_login_is_required(anon: Env) -> None:
    """No session: 401."""
    response = retry(anon, UNKNOWN_ID, 2, headers={})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_csrf_header_is_required(env: Env, failed: str) -> None:
    """Logged in, no token: 403 and nothing changes."""
    response = retry(env, failed, 3, headers={})
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"
    assert env.queue.rows == []


def test_retry_is_audited_without_personal_data(
    env: Env, db: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """One new audit entry mentioning retry; canary name and ID appear nowhere."""
    batch_id = running_batch(env, [[CANARY_NAME, CANARY_ID], ["Asha", "A2"]])
    set_rows(db, batch_id, [2], status="FAILED", failure_code="TTS_FAILED")
    before = audit_actions(env)
    with caplog.at_level(logging.DEBUG):
        assert retry(env, batch_id, 2).status_code == 200
    new = audit_actions(env)[len(before) :]
    assert len(new) == 1
    assert "RETRY" in new[0]
    entries = env.client.get("/audit").text
    assert CANARY_NAME not in entries
    assert CANARY_ID not in entries
    assert CANARY_NAME not in caplog.text
    assert CANARY_ID not in caplog.text
