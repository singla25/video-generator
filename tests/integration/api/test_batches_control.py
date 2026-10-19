"""Pause, resume, cancel, retry-failed (AC13, A6)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine

from tests.integration.api.batch_helpers import (
    counts_of,
    get_batch,
    new_batch,
    people,
    post_action,
    row_ids,
    row_status,
    running_batch,
    set_rows,
)
from tests.integration.api.conftest import Env
from tests.integration.api.helpers import audit_actions

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


# ---- pause and resume -----------------------------------------------------------------


def test_pause_then_resume_changes_only_the_batch_state(env: Env, db: Engine) -> None:
    """TT-AC13-P1, P2."""
    batch_id = running_batch(env, people(3))
    paused = post_action(env, batch_id, "pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"
    assert counts_of(env, batch_id)["queued"] == 3  # nothing started or dropped
    resumed = post_action(env, batch_id, "resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "RUNNING"


def test_pausing_twice_is_idempotent(env: Env) -> None:
    """TT-AC13-E3."""
    batch_id = running_batch(env)
    post_action(env, batch_id, "pause")
    again = post_action(env, batch_id, "pause")
    assert again.status_code == 200
    assert again.json()["status"] == "PAUSED"


def test_resume_of_a_batch_that_is_not_paused_is_409(env: Env) -> None:
    """TT-AC13-N2."""
    batch_id = running_batch(env)
    response = post_action(env, batch_id, "resume")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


@pytest.mark.parametrize("action", ["pause", "resume", "retry-failed"])
def test_control_actions_on_a_draft_batch_are_409(env: Env, action: str) -> None:
    """TT-AC13-N1: nothing to control before start."""
    response = post_action(env, new_batch(env), action)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


@pytest.mark.parametrize("action", ["pause", "resume", "cancel", "retry-failed"])
def test_unknown_batch_is_404(env: Env, action: str) -> None:
    """TT-AC13-N4."""
    response = post_action(env, UNKNOWN_ID, action)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_paused_batch_stays_paused_after_a_new_app_instance(env: Env) -> None:
    """TT-AC13-E8: the state is in the database."""
    batch_id = running_batch(env)
    post_action(env, batch_id, "pause")
    other = env.new_instance()
    other.login()
    assert get_batch(other, batch_id)["status"] == "PAUSED"


# ---- cancel (A6) ----------------------------------------------------------------------


def test_cancel_turns_only_queued_rows_into_cancelled(env: Env, db: Engine) -> None:
    """TT-AC13-P3, P6, E1 (A6): PROCESSING and COMPLETED rows are left alone."""
    batch_id = running_batch(env, people(5))
    set_rows(db, batch_id, [2], status="COMPLETED")
    set_rows(db, batch_id, [3, 4], status="PROCESSING")
    response = post_action(env, batch_id, "cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert row_status(db, batch_id) == {
        2: "COMPLETED",
        3: "PROCESSING",
        4: "PROCESSING",
        5: "CANCELLED",
        6: "CANCELLED",
    }


def test_counts_after_cancel_still_add_up_and_include_cancelled(env: Env, db: Engine) -> None:
    """TT-AC13-E7, AC14-P1."""
    batch_id = running_batch(env, [["Asha", "A1"], ["", "B2"], ["Chand", "C3"], ["Dev", "D4"]])
    set_rows(db, batch_id, [2], status="PROCESSING")
    post_action(env, batch_id, "cancel")
    counts = counts_of(env, batch_id)
    assert counts["cancelled"] == 2
    assert counts["processing"] == 1
    assert counts["skipped"] == 1
    assert counts["total"] == 4
    assert sum(v for k, v in counts.items() if k != "total") == counts["total"]


def test_cancel_works_on_a_paused_batch(env: Env) -> None:
    """TT-AC13-E2."""
    batch_id = running_batch(env)
    post_action(env, batch_id, "pause")
    assert post_action(env, batch_id, "cancel").json()["status"] == "CANCELLED"


def test_cancel_on_a_draft_batch_is_allowed_and_cancels_its_rows(env: Env, db: Engine) -> None:
    """TT-AC13-E4: cancelling before start discards the queued rows."""
    batch_id = new_batch(env, people(2))
    response = post_action(env, batch_id, "cancel")
    assert response.status_code == 200
    assert set(row_status(db, batch_id).values()) == {"CANCELLED"}


def test_cancelling_twice_is_idempotent(env: Env) -> None:
    """TT-AC13-E3."""
    batch_id = running_batch(env)
    post_action(env, batch_id, "cancel")
    again = post_action(env, batch_id, "cancel")
    assert again.status_code == 200
    assert again.json()["status"] == "CANCELLED"


@pytest.mark.parametrize("action", ["pause", "resume"])
def test_a_cancelled_batch_cannot_be_paused_or_resumed(env: Env, action: str) -> None:
    """TT-AC13-N1, E2."""
    batch_id = running_batch(env)
    post_action(env, batch_id, "cancel")
    response = post_action(env, batch_id, action)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


def test_cancel_with_nothing_left_queued_changes_no_rows(env: Env, db: Engine) -> None:
    """TT-AC13-E4."""
    batch_id = running_batch(env, people(2))
    set_rows(db, batch_id, [2, 3], status="COMPLETED")
    post_action(env, batch_id, "cancel")
    assert set(row_status(db, batch_id).values()) == {"COMPLETED"}


def test_cancelling_a_thousand_row_batch_is_a_bulk_operation(env: Env, db: Engine) -> None:
    """TT-AC13-E9."""
    import time

    batch_id = running_batch(env, people(1000))
    started = time.perf_counter()
    assert post_action(env, batch_id, "cancel").status_code == 200
    assert time.perf_counter() - started < 5
    assert counts_of(env, batch_id)["cancelled"] == 1000


# ---- retry failed ---------------------------------------------------------------------


def test_retry_failed_requeues_only_failed_rows(env: Env, db: Engine) -> None:
    """TT-AC13-P4."""
    batch_id = running_batch(
        env, [["Asha", "A1"], ["", "B2"], ["Chand", "C3"], ["Dev", "D4"], ["Esha", "E5"]]
    )
    env.queue.rows.clear()
    set_rows(db, batch_id, [2], status="COMPLETED")
    set_rows(db, batch_id, [4, 5], status="FAILED", failure_code="TTS_FAILED")
    response = post_action(env, batch_id, "retry-failed")
    assert response.status_code == 200
    assert response.json()["retried_rows"] == 2
    ids = row_ids(db, batch_id)
    assert sorted(row_id for _, row_id in env.queue.rows) == sorted([ids[4], ids[5]])
    statuses = row_status(db, batch_id)
    assert (statuses[2], statuses[3], statuses[4], statuses[5]) == (
        "COMPLETED",
        "SKIPPED",
        "QUEUED",
        "QUEUED",
    )


def test_retry_failed_clears_the_old_failure_code(env: Env, db: Engine) -> None:
    """TT-AC13-P4: the rows list shows a fresh state."""
    batch_id = running_batch(env, people(1))
    set_rows(db, batch_id, [2], status="FAILED", failure_code="STORAGE_ERROR")
    post_action(env, batch_id, "retry-failed")
    rows = env.client.get(f"/batches/{batch_id}/rows").json()["rows"]
    assert rows[0]["status"] == "QUEUED"
    assert rows[0]["failure_code"] is None


def test_retry_failed_without_failed_rows_queues_nothing(env: Env) -> None:
    """TT-AC13-N3."""
    batch_id = running_batch(env, people(2))
    queued_before = len(env.queue.rows)
    response = post_action(env, batch_id, "retry-failed")
    assert response.status_code == 200
    assert response.json()["retried_rows"] == 0
    assert len(env.queue.rows) == queued_before


def test_retrying_twice_quickly_queues_each_row_once(env: Env, db: Engine) -> None:
    """TT-AC13-E5."""
    batch_id = running_batch(env, people(2))
    env.queue.rows.clear()
    set_rows(db, batch_id, [2], status="FAILED", failure_code="TTS_FAILED")
    post_action(env, batch_id, "retry-failed")
    post_action(env, batch_id, "retry-failed")
    assert len(env.queue.rows) == 1


def test_retry_failed_on_a_cancelled_batch_is_409(env: Env, db: Engine) -> None:
    """TT-AC13-N1."""
    batch_id = running_batch(env, people(2))
    set_rows(db, batch_id, [2], status="FAILED", failure_code="TTS_FAILED")
    post_action(env, batch_id, "cancel")
    assert post_action(env, batch_id, "retry-failed").status_code == 409


def test_control_actions_are_audited_without_personal_data(env: Env) -> None:
    """C4."""
    batch_id = running_batch(env)
    post_action(env, batch_id, "pause")
    post_action(env, batch_id, "resume")
    post_action(env, batch_id, "cancel")
    actions = audit_actions(env)
    for expected in ("BATCH_PAUSED", "BATCH_RESUMED", "BATCH_CANCELLED"):
        assert expected in actions
    entry = env.client.get("/audit", params={"action": "BATCH_CANCELLED"}).json()["entries"][0]
    assert entry["details"]["batch_id"] == batch_id
    assert UUID(entry["details"]["batch_id"])
