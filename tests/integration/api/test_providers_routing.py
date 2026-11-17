"""RP-RTE (API): every job of a batch goes to the chosen provider's queue only (AC6).

Contract: ``queue_name`` is passed to the JobQueue only for batches that have a provider; old
  batches
(provider null) use the legacy call shape (no queue name = default queue).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from tests.integration.api.batch_helpers import (
    get_batch,
    row_ids,
    running_batch,
    set_rows,
)
from tests.integration.api.conftest import Env
from tests.integration.api.provider_helpers import (
    LOCAL_QUEUE,
    MODAL_QUEUE,
    approve_with,
    build_env,
    demo_batch,
    render_preview,
    start_batch,
    started_with,
)


@pytest.fixture
def env(db: Engine, test_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return build_env(db, test_db_url, tmp_path, monkeypatch)


def retry_failed(env: Env, batch_id: str):  # type: ignore[no-untyped-def]
    return env.client.post(f"/batches/{batch_id}/retry-failed", headers=env.csrf)


def change_provider(env: Env, batch_id: str, provider_id: str):  # type: ignore[no-untyped-def]
    return env.client.put(
        f"/batches/{batch_id}/provider", json={"provider_id": provider_id}, headers=env.csrf
    )


# ---- positive -------------------------------------------------------------------------


def test_start_sends_every_row_to_the_chosen_providers_queue_only(env: Env) -> None:
    """RP-RTE-P3."""
    started_with(env, "modal-demo")
    assert len(env.queue.rows) == 3
    assert env.queue.queues_used() == {MODAL_QUEUE}


def test_a_different_choice_uses_its_own_queue(env: Env) -> None:
    """RP-RTE-P4."""
    started_with(env, "local-mac")
    assert env.queue.queues_used() == {LOCAL_QUEUE}


def test_retry_failed_and_per_row_retry_follow_the_batch_provider(env: Env, db: Engine) -> None:
    """RP-RTE-P6."""
    batch_id = started_with(env, "modal-demo")
    numbers = sorted(row_ids(db, batch_id))
    set_rows(db, batch_id, numbers[:2], status="FAILED", failure_code="TTS_FAILED")
    env.queue.routed.clear()
    assert retry_failed(env, batch_id).status_code == 200
    assert {q for *_x, q in env.queue.routed} == {MODAL_QUEUE}
    assert len(env.queue.routed) == 2
    set_rows(db, batch_id, numbers[:1], status="FAILED", failure_code="TTS_FAILED")
    env.queue.routed.clear()
    response = env.client.post(f"/batches/{batch_id}/rows/{numbers[0]}/retry", headers=env.csrf)
    assert response.status_code == 200, response.text
    assert [q for *_x, q in env.queue.routed] == [MODAL_QUEUE]


def test_the_default_provider_batch_keeps_the_legacy_call_shape(env: Env) -> None:
    """RP-RTE-E3 (R5): a batch started without a provider passes no queue name."""
    running_batch(env)
    assert env.queue.queues_used() == {None}


# ---- negative -------------------------------------------------------------------------


def test_nothing_reaches_another_providers_queue(env: Env) -> None:
    """RP-RTE-N3."""
    started_with(env, "modal-demo")
    assert LOCAL_QUEUE not in env.queue.queues_used()
    assert None not in env.queue.queues_used()


def test_the_provider_cannot_change_while_the_batch_is_running(env: Env) -> None:
    """RP-RTE-N4."""
    batch_id = started_with(env, "modal-demo")
    response = change_provider(env, batch_id, "local-mac")
    assert (response.status_code, response.json()["code"]) == (409, "INVALID_STATE")
    assert get_batch(env, batch_id)["provider_id"] == "modal-demo"


def test_a_change_to_a_provider_that_is_refused_changes_nothing(env: Env, db: Engine) -> None:
    """RP-RTE-N5: unknown id -> 422; demo_only for a real batch -> 409."""
    batch_id = started_with(env, "local-mac", demo=False)
    assert env.client.post(f"/batches/{batch_id}/pause", headers=env.csrf).status_code == 200
    env.queue.routed.clear()
    assert change_provider(env, batch_id, "ghost").status_code == 422
    response = change_provider(env, batch_id, "modal-demo")
    assert (response.status_code, response.json()["code"]) == (409, "PROVIDER_NOT_ALLOWED")
    assert get_batch(env, batch_id)["provider_id"] == "local-mac"
    assert env.queue.routed == []


# ---- edge -----------------------------------------------------------------------------


def test_changing_the_provider_while_paused_moves_the_queued_rows(env: Env, db: Engine) -> None:
    """RP-RTE-E1: queued rows are enqueued on the new queue; finished rows are not touched."""
    batch_id = started_with(env, "modal-demo")
    ids = row_ids(db, batch_id)
    numbers = sorted(ids)
    set_rows(db, batch_id, numbers[:1], status="COMPLETED")
    assert env.client.post(f"/batches/{batch_id}/pause", headers=env.csrf).status_code == 200
    env.queue.routed.clear()
    response = change_provider(env, batch_id, "local-mac")
    assert response.status_code == 200, response.text
    assert response.json()["provider_id"] == "local-mac"
    moved = {row for _k, _b, row, _q in env.queue.routed}
    assert moved == {ids[n] for n in numbers[1:]}
    assert env.queue.queues_used() == {LOCAL_QUEUE}


def test_a_draft_batch_can_change_provider_before_start(env: Env) -> None:
    """RP-RTE-E2: nothing is queued yet, so nothing moves."""
    batch_id = demo_batch(env)
    render_preview(env, batch_id)
    assert approve_with(env, batch_id, "modal-demo").status_code == 200
    assert change_provider(env, batch_id, "local-mac").status_code == 200
    assert env.queue.rows == []
    assert start_batch(env, batch_id).status_code == 200
    assert env.queue.queues_used() == {LOCAL_QUEUE}


def test_the_preview_job_is_queued_for_the_default_provider(env: Env) -> None:
    """RP-RTE-E8: the choice is made after the preview, so the preview uses the default queue."""
    batch_id = demo_batch(env)
    render_preview(env, batch_id)
    assert env.queue.queues_used("preview") == {None}
