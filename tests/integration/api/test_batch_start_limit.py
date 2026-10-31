"""Start with a limit: the first N queued rows are queued, the rest are NOT_SELECTED (DD-37)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import Response
from sqlalchemy import Engine

from tests.integration.api.batch_helpers import (
    approve_preview,
    get_batch,
    new_batch,
    people,
    row_ids,
    row_status,
    start,
)
from tests.integration.api.conftest import Env

NOT_SELECTED_MESSAGE = "Not selected: outside the number of videos requested."
NOT_SELECTED = "NOT_SELECTED"


def start_with(env: Env, batch_id: str, body: dict[str, Any], *, key: str = "key-1") -> Response:
    """POST /batches/{id}/start with a JSON body and an Idempotency-Key."""
    headers = {**env.csrf, "Idempotency-Key": key}
    return env.client.post(f"/batches/{batch_id}/start", json=body, headers=headers)


def ready_batch(env: Env, rows: list[list[str]] | None = None) -> str:
    """A batch with an approved preview, not started yet; five valid rows by default."""
    batch_id = new_batch(env, rows if rows is not None else people(5))
    approve_preview(env, batch_id)
    return batch_id


def rows_by_number(env: Env, batch_id: str) -> dict[int, dict[str, Any]]:
    """GET /batches/{id}/rows keyed by sheet row number."""
    response = env.client.get(f"/batches/{batch_id}/rows")
    assert response.status_code == 200, response.text
    return {row["row_number"]: row for row in response.json()["rows"]}


def audit_entries(env: Env, action: str) -> list[dict[str, Any]]:
    """Audit entries of one action, oldest first."""
    response = env.client.get("/audit", params={"action": action})
    assert response.status_code == 200, response.text
    entries: list[dict[str, Any]] = response.json()["entries"]
    return entries


# ---- positive -------------------------------------------------------------------------


def test_limit_two_of_five_rows_leaves_two_queued_and_three_skipped(env: Env) -> None:
    """DD-37 P1: the start response counts reflect the selection."""
    batch_id = ready_batch(env)
    response = start_with(env, batch_id, {"limit": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["queued_rows"] == 2
    assert (body["counts"]["queued"], body["counts"]["skipped"]) == (2, 3)


def test_the_first_rows_by_row_number_are_the_queued_ones(env: Env) -> None:
    """DD-37 P2: rows 2 and 3 (lowest row numbers) stay QUEUED; 4, 5 and 6 are skipped."""
    batch_id = ready_batch(env)
    assert start_with(env, batch_id, {"limit": 2}).status_code == 200
    rows = rows_by_number(env, batch_id)
    assert [rows[n]["status"] for n in (2, 3)] == ["QUEUED", "QUEUED"]
    assert [rows[n]["status"] for n in (4, 5, 6)] == ["SKIPPED", "SKIPPED", "SKIPPED"]


def test_not_selected_rows_carry_the_code_and_the_exact_message(env: Env) -> None:
    """DD-37 P3: read back through the rows endpoint; queued rows have no failure."""
    batch_id = ready_batch(env)
    assert start_with(env, batch_id, {"limit": 2}).status_code == 200
    rows = rows_by_number(env, batch_id)
    for number in (4, 5, 6):
        assert rows[number]["failure_code"] == NOT_SELECTED, number
        assert rows[number]["message"] == NOT_SELECTED_MESSAGE, number
    for number in (2, 3):
        assert rows[number]["failure_code"] is None, number
        assert rows[number]["message"] is None, number


def test_only_the_selected_rows_are_enqueued(env: Env, db: Engine) -> None:
    """DD-37 P4: the fake queue receives exactly the two selected row ids."""
    batch_id = ready_batch(env)
    assert start_with(env, batch_id, {"limit": 2}).status_code == 200
    ids = row_ids(db, batch_id)
    assert {bid for bid, _ in env.queue.rows} == {UUID(batch_id)}
    assert sorted(row_id for _, row_id in env.queue.rows) == sorted([ids[2], ids[3]])


def test_default_folder_name_counts_the_selected_rows(env: Env) -> None:
    """DD-37 P5: the default folder uses the number of selected rows (2), not the sheet (5)."""
    batch_id = ready_batch(env)
    assert start_with(env, batch_id, {"limit": 2}).json()["folder_name"] == "2026-10-18-2"


def test_custom_folder_name_is_still_used_with_a_limit(env: Env) -> None:
    """DD-37 P6: folder_name and limit can be sent together."""
    batch_id = ready_batch(env)
    body = start_with(env, batch_id, {"limit": 2, "folder_name": "Ward 12"}).json()
    assert body["folder_name"] == "Ward 12"
    assert body["queued_rows"] == 2


@pytest.mark.parametrize("limit", [5, 6, 100])
def test_limit_at_or_above_the_queued_rows_skips_nothing(env: Env, limit: int) -> None:
    """DD-37 P7: a limit that covers every queued row changes nothing."""
    batch_id = ready_batch(env)
    body = start_with(env, batch_id, {"limit": limit}).json()
    assert body["queued_rows"] == 5
    assert (body["counts"]["queued"], body["counts"]["skipped"]) == (5, 0)
    assert all(row["failure_code"] is None for row in rows_by_number(env, batch_id).values())
    assert len(env.queue.rows) == 5


def test_without_a_limit_every_valid_row_is_queued_as_before(env: Env) -> None:
    """DD-37 P8: no limit is today's behaviour; folder counts all five rows."""
    batch_id = ready_batch(env)
    response = start(env, batch_id)
    assert response.status_code == 200
    body = response.json()
    assert body["queued_rows"] == 5
    assert (body["counts"]["queued"], body["counts"]["skipped"]) == (5, 0)
    assert body["folder_name"] == "2026-10-18-5"
    assert len(env.queue.rows) == 5


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [0, -1, "abc", 2.5])
def test_invalid_limit_is_422_and_nothing_is_changed(env: Env, db: Engine, limit: Any) -> None:
    """DD-37 N1: limit must be an integer >= 1; the batch stays a draft with every row queued."""
    batch_id = ready_batch(env)
    response = start_with(env, batch_id, {"limit": limit})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert get_batch(env, batch_id)["status"] == "DRAFT"
    assert env.queue.rows == []
    assert set(row_status(db, batch_id).values()) == {"QUEUED"}


# ---- edge -----------------------------------------------------------------------------


def test_limit_of_one_queues_only_the_first_row(env: Env) -> None:
    """DD-37 E1: the smallest allowed limit."""
    batch_id = ready_batch(env)
    body = start_with(env, batch_id, {"limit": 1}).json()
    assert (body["queued_rows"], body["counts"]["skipped"]) == (1, 4)
    assert rows_by_number(env, batch_id)[2]["status"] == "QUEUED"


def test_limit_counts_only_queued_rows_and_invalid_rows_keep_their_own_reason(
    env: Env, db: Engine
) -> None:
    """DD-37 E2: invalid row 3 keeps its own reason and does not use up a slot."""
    rows = [["Asha", "A1"], ["", "B2"], ["Chand", "C3"], ["Dev", "D4"]]
    batch_id = ready_batch(env, rows)
    assert start_with(env, batch_id, {"limit": 2}).status_code == 200
    statuses = rows_by_number(env, batch_id)
    assert [statuses[n]["status"] for n in (2, 4)] == ["QUEUED", "QUEUED"]
    assert statuses[3]["status"] == "SKIPPED"
    assert statuses[3]["failure_code"] == "INVALID_ROW_EMPTY_NAME"
    assert statuses[5]["failure_code"] == NOT_SELECTED
    ids = row_ids(db, batch_id)
    assert sorted(row_id for _, row_id in env.queue.rows) == sorted([ids[2], ids[4]])


def test_repeating_the_same_limited_start_does_not_skip_more_rows(env: Env) -> None:
    """DD-37 E3: the same Idempotency-Key returns the same state and no new skips or jobs."""
    batch_id = ready_batch(env)
    first = start_with(env, batch_id, {"limit": 2}, key="same")
    second = start_with(env, batch_id, {"limit": 2}, key="same")
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    rows = rows_by_number(env, batch_id)
    assert sum(1 for row in rows.values() if row["failure_code"] == NOT_SELECTED) == 3
    assert len(env.queue.rows) == 2
    assert len(audit_entries(env, "BATCH_STARTED")) == 1


def test_another_key_on_a_started_batch_with_a_smaller_limit_changes_nothing(
    env: Env, db: Engine
) -> None:
    """DD-37 E4: a started batch is a no-op for later starts (existing rule B11)."""
    batch_id = ready_batch(env)
    assert start_with(env, batch_id, {"limit": 2}, key="one").status_code == 200
    before = row_status(db, batch_id)
    again = start_with(env, batch_id, {"limit": 1}, key="two")
    assert again.status_code == 200
    assert again.json()["counts"]["skipped"] == 3
    assert row_status(db, batch_id) == before
    assert len(env.queue.rows) == 2


# ---- audit ----------------------------------------------------------------------------


def test_batch_started_audit_records_limit_and_skipped_rows(env: Env) -> None:
    """DD-37: BATCH_STARTED carries the limit and the skipped count as numbers only."""
    batch_id = ready_batch(env)
    assert start_with(env, batch_id, {"limit": 2}).status_code == 200
    entries = audit_entries(env, "BATCH_STARTED")
    assert len(entries) == 1
    details = entries[0]["details"]
    assert details["limit"] == 2
    assert details["skipped_rows"] == 3
    assert isinstance(details["limit"], int)
    assert isinstance(details["skipped_rows"], int)


def test_batch_started_audit_without_a_limit_records_zero_skipped(env: Env) -> None:
    """DD-37: a start without a limit still records skipped_rows, as 0."""
    batch_id = ready_batch(env)
    assert start(env, batch_id).status_code == 200
    details = audit_entries(env, "BATCH_STARTED")[0]["details"]
    assert details["skipped_rows"] == 0
