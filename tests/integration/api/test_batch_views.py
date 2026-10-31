"""Batch list filtered by lifecycle view: all, running, completed, failed (DD-37).

Meaning of the views on the batch ``status`` and the FAILED row count:
- running:   status RUNNING or PAUSED (a failed row does not remove it from running)
- completed: status COMPLETED and no FAILED row
- failed:    status RUNNING, PAUSED or COMPLETED with at least one FAILED row
- DRAFT and CANCELLED batches appear in none of the three filtered views.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from tests.integration.api.batch_helpers import (
    approve_preview,
    new_batch,
    people,
    post_action,
    set_batch,
    set_rows,
    start,
    usable_template,
)
from tests.integration.api.conftest import Env

PAGE_SIZE = 50
ALL_LABELS = frozenset(
    {
        "draft",
        "draft_failed",
        "running",
        "running_failed",
        "paused",
        "paused_failed",
        "completed",
        "completed_failed",
        "cancelled",
        "cancelled_failed",
    }
)
RUNNING_VIEW = frozenset({"running", "running_failed", "paused", "paused_failed"})
COMPLETED_VIEW = frozenset({"completed"})
FAILED_VIEW = frozenset({"running_failed", "paused_failed", "completed_failed"})
NEVER_FILTERED = frozenset({"draft", "draft_failed", "cancelled", "cancelled_failed"})


def running_batch(env: Env, template_id: str) -> str:
    """An approved and started batch; each start gets its own Idempotency-Key."""
    batch_id = new_batch(env, people(3), template_id=template_id)
    approve_preview(env, batch_id)
    assert start(env, batch_id, key=uuid4().hex).status_code == 200
    return batch_id


def fail_first_row(db: Engine, batch_id: str) -> str:
    """Give row 2 (the first data row) the FAILED status the way the worker would."""
    set_rows(db, batch_id, [2], status="FAILED", failure_code="TTS_FAILED")
    return batch_id


def build_fleet(env: Env, db: Engine) -> dict[str, str]:
    """One batch per lifecycle state, with and without a FAILED row; label -> batch id."""
    template_id = usable_template(env)

    def sheet() -> str:
        return new_batch(env, people(3), template_id=template_id)

    def completed() -> str:
        batch_id = running_batch(env, template_id)
        set_batch(db, batch_id, status="COMPLETED")
        return batch_id

    def cancelled() -> str:
        batch_id = sheet()
        post_action(env, batch_id, "cancel")
        return batch_id

    def paused() -> str:
        batch_id = running_batch(env, template_id)
        post_action(env, batch_id, "pause")
        return batch_id

    return {
        "draft": sheet(),
        "draft_failed": fail_first_row(db, sheet()),
        "running": running_batch(env, template_id),
        "running_failed": fail_first_row(db, running_batch(env, template_id)),
        "paused": paused(),
        "paused_failed": fail_first_row(db, paused()),
        "completed": completed(),
        "completed_failed": fail_first_row(db, completed()),
        "cancelled": cancelled(),
        "cancelled_failed": fail_first_row(db, cancelled()),
    }


def listing(env: Env, **params: Any) -> dict[str, Any]:
    """GET /batches with a page size large enough for the fleet."""
    response = env.client.get("/batches", params={"page_size": PAGE_SIZE, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def labels_in(env: Env, fleet: dict[str, str], view: str) -> frozenset[str]:
    """The fleet labels of the batches the given view lists."""
    label_of = {batch_id: label for label, batch_id in fleet.items()}
    batches = listing(env, view=view)["batches"]
    return frozenset(label_of[batch["id"]] for batch in batches)


# ---- positive: one test per view value ------------------------------------------------


def test_view_all_lists_every_batch_in_every_state(env: Env, db: Engine) -> None:
    """DD-37 view=all: drafts, cancelled and failed batches included."""
    fleet = build_fleet(env, db)
    assert labels_in(env, fleet, "all") == ALL_LABELS


def test_view_running_lists_running_and_paused_batches(env: Env, db: Engine) -> None:
    """DD-37 view=running: RUNNING or PAUSED, with or without failed rows."""
    fleet = build_fleet(env, db)
    assert labels_in(env, fleet, "running") == RUNNING_VIEW


def test_view_completed_lists_completed_batches_without_failed_rows(env: Env, db: Engine) -> None:
    """DD-37 view=completed: COMPLETED with zero FAILED rows only."""
    fleet = build_fleet(env, db)
    assert labels_in(env, fleet, "completed") == COMPLETED_VIEW


def test_view_failed_lists_started_batches_with_at_least_one_failed_row(
    env: Env, db: Engine
) -> None:
    """DD-37 view=failed: RUNNING, PAUSED or COMPLETED that have a FAILED row."""
    fleet = build_fleet(env, db)
    assert labels_in(env, fleet, "failed") == FAILED_VIEW


# ---- positive: overlap and exclusions -------------------------------------------------


def test_running_batch_with_a_failed_row_is_listed_under_running_and_failed(
    env: Env, db: Engine
) -> None:
    """DD-37: a running batch with one failed row appears in both views."""
    fleet = build_fleet(env, db)
    assert fleet["running_failed"] in {b["id"] for b in listing(env, view="running")["batches"]}
    assert fleet["running_failed"] in {b["id"] for b in listing(env, view="failed")["batches"]}
    # The overlap is counted in both totals, not once per view.
    assert listing(env, view="running")["total"] == len(RUNNING_VIEW)
    assert listing(env, view="failed")["total"] == len(FAILED_VIEW)


@pytest.mark.parametrize("view", ["running", "completed", "failed"])
def test_draft_and_cancelled_batches_never_appear_in_the_filtered_views(
    env: Env, db: Engine, view: str
) -> None:
    """DD-37: DRAFT and CANCELLED batches, with or without FAILED rows, are never listed."""
    fleet = build_fleet(env, db)
    assert labels_in(env, fleet, view).isdisjoint(NEVER_FILTERED)


def test_view_all_is_exactly_the_unfiltered_listing(env: Env, db: Engine) -> None:
    """DD-37: view=all returns what GET /batches returns without the parameter."""
    build_fleet(env, db)
    unfiltered = env.client.get("/batches")
    everything = env.client.get("/batches", params={"view": "all"})
    assert unfiltered.status_code == everything.status_code == 200
    assert everything.json() == unfiltered.json()


# ---- positive: paging and totals under a filter ---------------------------------------


def test_pages_under_a_filter_hold_only_matching_batches_newest_first(env: Env, db: Engine) -> None:
    """DD-37: page_size 1 walks the running batches only, newest first."""
    template_id = usable_template(env)
    created: list[str] = []
    for index in range(4):
        created.append(running_batch(env, template_id))
        env.clock.advance(minutes=1)
        if index == 1:  # a completed batch between running ones must not take a page slot
            done = new_batch(env, people(2), template_id=template_id)
            set_batch(db, done, status="COMPLETED")
            env.clock.advance(minutes=1)
    newest_first = list(reversed(created))
    seen: list[str] = []
    for page in range(1, 5):
        body = listing(env, view="running", page=page, page_size=1)
        assert (body["page"], body["page_size"]) == (page, 1)
        assert (body["total"], body["total_pages"]) == (4, 4)
        seen.extend(batch["id"] for batch in body["batches"])
    assert seen == newest_first


def test_totals_count_only_the_filtered_batches(env: Env, db: Engine) -> None:
    """DD-37: total and total_pages follow the filter, not the whole history."""
    build_fleet(env, db)
    assert (listing(env)["total"], listing(env)["total_pages"]) == (10, 1)
    failed = listing(env, view="failed", page_size=1)
    assert (failed["total"], failed["total_pages"]) == (3, 3)
    assert len(failed["batches"]) == 1
    completed = listing(env, view="completed", page_size=1)
    assert (completed["total"], completed["total_pages"]) == (1, 1)


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize("view", ["bogus", "RUNNING", "Failed", "queued", "all,running", ""])
def test_unknown_view_value_is_a_validation_error(env: Env, view: str) -> None:
    """DD-37: any value other than all, running, completed or failed is 422."""
    response = env.client.get("/batches", params={"view": view})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---- edge -----------------------------------------------------------------------------


def test_view_with_no_matching_batches_is_an_empty_page(env: Env) -> None:
    """DD-37 edge: a filter that matches nothing still returns 200 with zero totals."""
    new_batch(env, people(2))
    body = listing(env, view="completed")
    assert body["batches"] == []
    assert body["total"] == 0


def test_view_on_an_empty_history_is_empty(env: Env) -> None:
    """DD-37 edge: no batches at all."""
    body = listing(env, view="failed")
    assert body["batches"] == []
    assert body["total"] == 0
