"""DD-38: GET /batches?view=drafts lists only the DRAFT batches, newest first.

The drafts view joins the existing views (all, running, completed, failed). The existing
views keep their meaning and never list drafts; view=all still lists everything.
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
)
from tests.integration.api.conftest import Env

PAGE_SIZE = 50
EXISTING_FILTERED_VIEWS = ("running", "completed", "failed")
STARTED_OR_FINISHED = ("running", "paused", "completed", "cancelled")


def listing(env: Env, **params: Any) -> dict[str, Any]:
    """GET /batches with a page size large enough for the fixtures."""
    response = env.client.get("/batches", params={"page_size": PAGE_SIZE, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def ids_in(env: Env, view: str) -> list[str]:
    """Batch ids of one view, in the order the API returns them."""
    return [batch["id"] for batch in listing(env, view=view)["batches"]]


def fail_first_row(db: Engine, batch_id: str) -> str:
    """Give row 2 (the first data row) the FAILED status the way the worker would."""
    set_rows(db, batch_id, [2], status="FAILED", failure_code="TTS_FAILED")
    return batch_id


def started_batch(env: Env) -> str:
    """An approved and started batch; every start gets its own Idempotency-Key."""
    batch_id = new_batch(env, people(3))
    approve_preview(env, batch_id)
    assert start(env, batch_id, key=uuid4().hex).status_code == 200
    return batch_id


def batch_in_state(env: Env, db: Engine, state: str) -> str:
    """A batch in the given lifecycle state, created with its own clock tick."""
    if state == "draft":
        batch_id = new_batch(env, people(3))
    elif state == "running":
        batch_id = started_batch(env)
    elif state == "paused":
        batch_id = started_batch(env)
        assert post_action(env, batch_id, "pause").status_code == 200
    elif state == "completed":
        batch_id = started_batch(env)
        set_batch(db, batch_id, status="COMPLETED")
    else:
        assert state == "cancelled"
        batch_id = new_batch(env, people(3))
        assert post_action(env, batch_id, "cancel").status_code == 200
    env.clock.advance(minutes=1)
    return batch_id


# ---- positive -------------------------------------------------------------------------


def test_drafts_view_lists_only_draft_batches(env: Env, db: Engine) -> None:
    """DD-38 D-P1: DRAFT batches are listed, with or without a FAILED row or a pending preview."""
    plain = batch_in_state(env, db, "draft")
    with_failed_row = fail_first_row(db, batch_in_state(env, db, "draft"))
    previewing = batch_in_state(env, db, "draft")
    assert post_action(env, previewing, "preview").status_code == 202
    for state in STARTED_OR_FINISHED:
        batch_in_state(env, db, state)
    assert set(ids_in(env, "drafts")) == {plain, with_failed_row, previewing}


def test_drafts_view_is_newest_first(env: Env, db: Engine) -> None:
    """DD-38 D-P2: drafts are ordered by creation time, newest first, with other batches between."""
    created: list[str] = []
    for index in range(4):
        created.append(batch_in_state(env, db, "draft"))
        if index == 1:
            batch_in_state(env, db, "running")
    assert ids_in(env, "drafts") == list(reversed(created))


def test_drafts_pages_walk_only_drafts_newest_first(env: Env, db: Engine) -> None:
    """DD-38 D-P3: page_size 1 walks the drafts; totals count drafts only."""
    created: list[str] = []
    for _ in range(3):
        created.append(batch_in_state(env, db, "draft"))
        batch_in_state(env, db, "completed")
    seen: list[str] = []
    for page in range(1, 4):
        body = listing(env, view="drafts", page=page, page_size=1)
        assert (body["page"], body["page_size"]) == (page, 1)
        assert (body["total"], body["total_pages"]) == (3, 3)
        seen.extend(batch["id"] for batch in body["batches"])
    assert seen == list(reversed(created))


def test_view_all_still_lists_drafts(env: Env, db: Engine) -> None:
    """DD-38 D-P4: the unfiltered view keeps listing drafts alongside everything else."""
    draft = batch_in_state(env, db, "draft")
    running = batch_in_state(env, db, "running")
    assert {draft, running} <= set(ids_in(env, "all"))


@pytest.mark.parametrize("view", EXISTING_FILTERED_VIEWS)
def test_existing_views_never_list_drafts(env: Env, db: Engine, view: str) -> None:
    """DD-38 D-P5: running, completed and failed are unchanged and exclude drafts."""
    draft = batch_in_state(env, db, "draft")
    failed_draft = fail_first_row(db, batch_in_state(env, db, "draft"))
    for state in STARTED_OR_FINISHED:
        batch_in_state(env, db, state)
    listed = set(ids_in(env, view))
    assert draft not in listed
    assert failed_draft not in listed


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize("view", ["draft", "Drafts", "DRAFTS", "pending", "drafts,running"])
def test_unknown_view_value_including_singular_draft_is_422(env: Env, view: str) -> None:
    """DD-38 D-N1: only all, running, completed, failed and drafts are valid; 'draft' is not."""
    response = env.client.get("/batches", params={"view": view})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---- edge -----------------------------------------------------------------------------


@pytest.mark.parametrize("state", STARTED_OR_FINISHED)
def test_drafts_view_excludes_started_completed_and_cancelled(
    env: Env, db: Engine, state: str
) -> None:
    """DD-38 D-E1: a batch in any other state never appears; the draft still does."""
    draft = batch_in_state(env, db, "draft")
    other = batch_in_state(env, db, state)
    assert ids_in(env, "drafts") == [draft]
    assert other not in ids_in(env, "drafts")


def test_started_draft_leaves_the_drafts_view(env: Env, db: Engine) -> None:
    """DD-38 D-E2: once a draft is started it is no longer a draft."""
    batch_id = new_batch(env, people(2))
    approve_preview(env, batch_id)
    assert start(env, batch_id, key=uuid4().hex).status_code == 200
    assert ids_in(env, "drafts") == []


def test_drafts_view_with_no_drafts_is_empty(env: Env, db: Engine) -> None:
    """DD-38 D-E3: history exists, but nothing is a draft."""
    batch_in_state(env, db, "running")
    body = listing(env, view="drafts")
    assert body["batches"] == []
    assert body["total"] == 0


def test_drafts_view_on_an_empty_history_is_empty(env: Env) -> None:
    """DD-38 D-E4: no batches at all."""
    body = listing(env, view="drafts")
    assert body["batches"] == []
    assert (body["total"], body["total_pages"]) == (0, 0)


def test_page_past_the_end_keeps_the_drafts_total(env: Env, db: Engine) -> None:
    """DD-38 D-E5: a page after the last draft is empty but still reports the filtered total."""
    batch_in_state(env, db, "draft")
    batch_in_state(env, db, "draft")
    body = listing(env, view="drafts", page=3, page_size=1)
    assert body["batches"] == []
    assert (body["total"], body["total_pages"]) == (2, 2)
