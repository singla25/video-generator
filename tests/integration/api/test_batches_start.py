"""Preview gate and start: approval, invalidation, folders, idempotency (AC7, AC11, B4, B11)."""

from __future__ import annotations

import io
import threading
from uuid import UUID

import pytest
from sqlalchemy import Engine

from tests.integration.api.batch_helpers import (
    approve_preview,
    counts_of,
    create_batch,
    get_batch,
    new_batch,
    people,
    post_action,
    row_ids,
    row_status,
    start,
    usable_template,
)
from tests.integration.api.conftest import Env
from tests.integration.api.helpers import audit_actions, confirm_slot, set_slot
from vidgen.domain.codes import FailureCode

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def render_preview(env: Env, batch_id: str) -> None:
    """Simulate the worker finishing the preview render."""
    key = env.storage.write(f"previews/{batch_id}.mp4", io.BytesIO(b"PREVIEW-BYTES"))
    env.app.state.container.batches.preview_rendered(UUID(batch_id), key)


# ---- preview --------------------------------------------------------------------------


def test_preview_request_is_queued_not_rendered_in_the_request(env: Env, db: Engine) -> None:
    """TT-AC7-P1, N5: 202, one preview job for the first valid row."""
    batch_id = new_batch(env, [["", "A1"], ["Bina", "B2"], ["Chand", "C3"]])
    response = post_action(env, batch_id, "preview")
    assert response.status_code == 202
    assert response.json()["preview"] == {"status": "PENDING", "approved": False}
    assert env.queue.previews == [(UUID(batch_id), row_ids(db, batch_id)[3])]  # row 2 was invalid
    assert env.queue.rows == []


def test_preview_becomes_ready_when_the_worker_reports_it(env: Env) -> None:
    """TT-AC7-P1."""
    batch_id = new_batch(env)
    post_action(env, batch_id, "preview")
    render_preview(env, batch_id)
    assert get_batch(env, batch_id)["preview"] == {"status": "READY", "approved": False}


def test_ready_preview_can_be_downloaded(env: Env) -> None:
    """TT-AC7-P1."""
    batch_id = new_batch(env)
    post_action(env, batch_id, "preview")
    render_preview(env, batch_id)
    response = env.client.get(f"/batches/{batch_id}/preview")
    assert response.status_code == 200
    assert response.content == b"PREVIEW-BYTES"


def test_preview_download_before_ready_is_409(env: Env) -> None:
    """TT-AC7-N4."""
    batch_id = new_batch(env)
    response = env.client.get(f"/batches/{batch_id}/preview")
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_READY"


def test_approval_makes_start_possible_and_is_audited(env: Env) -> None:
    """TT-AC7-P2, P3."""
    batch_id = new_batch(env)
    approve_preview(env, batch_id)
    assert get_batch(env, batch_id)["preview"] == {"status": "READY", "approved": True}
    assert start(env, batch_id).status_code == 200
    actions = audit_actions(env)
    assert "PREVIEW_REQUESTED" in actions
    assert "PREVIEW_APPROVED" in actions
    assert "BATCH_STARTED" in actions


def test_approving_twice_is_idempotent_with_one_audit_entry(env: Env) -> None:
    """TT-AC7-E2."""
    batch_id = new_batch(env)
    approve_preview(env, batch_id)
    assert post_action(env, batch_id, "preview/approve").status_code == 200
    assert audit_actions(env).count("PREVIEW_APPROVED") == 1


def test_start_without_a_preview_is_409_and_queues_nothing(env: Env) -> None:
    """TT-AC7-N1."""
    batch_id = new_batch(env)
    response = start(env, batch_id)
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_APPROVED"
    assert env.queue.rows == []
    assert get_batch(env, batch_id)["status"] == "DRAFT"


def test_start_with_an_unapproved_preview_is_409(env: Env) -> None:
    """TT-AC7-N2."""
    batch_id = new_batch(env)
    post_action(env, batch_id, "preview")
    render_preview(env, batch_id)
    response = start(env, batch_id)
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_APPROVED"
    assert env.queue.rows == []


def test_approving_before_the_preview_is_ready_is_409(env: Env) -> None:
    """TT-AC7-N4."""
    batch_id = new_batch(env)
    post_action(env, batch_id, "preview")
    response = post_action(env, batch_id, "preview/approve")
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_READY"


def test_approving_without_requesting_a_preview_is_409(env: Env) -> None:
    """TT-AC7-N4."""
    response = post_action(env, new_batch(env), "preview/approve")
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_READY"


def test_failed_preview_blocks_start_and_can_be_requested_again(env: Env) -> None:
    """TT-AC7-N3."""
    batch_id = new_batch(env)
    post_action(env, batch_id, "preview")
    env.app.state.container.batches.preview_failed(UUID(batch_id), FailureCode.TTS_FAILED)
    assert get_batch(env, batch_id)["preview"]["status"] == "FAILED"
    assert start(env, batch_id).status_code == 409
    assert post_action(env, batch_id, "preview").status_code == 202
    assert len(env.queue.previews) == 2


def test_first_valid_row_is_the_preview_row(env: Env, db: Engine) -> None:
    """TT-AC7-P4."""
    batch_id = new_batch(env, [["Asha", "A1"], ["Bina", "B2"]])
    post_action(env, batch_id, "preview")
    assert env.queue.previews[0][1] == row_ids(db, batch_id)[2]


def test_batch_with_exactly_one_valid_row_can_be_previewed_and_started(env: Env) -> None:
    """TT-AC7-E1."""
    batch_id = new_batch(env, [["", "A1"], ["Bina", "B2"]])
    approve_preview(env, batch_id)
    assert start(env, batch_id).status_code == 200
    assert len(env.queue.rows) == 1


def test_preview_does_not_change_the_row_counts(env: Env) -> None:
    """B7: previews are excluded from counts."""
    batch_id = new_batch(env, people(3))
    before = counts_of(env, batch_id)
    post_action(env, batch_id, "preview")
    render_preview(env, batch_id)
    assert counts_of(env, batch_id) == before


def test_preview_for_unknown_batch_is_404(env: Env) -> None:
    """TT-AC7-N1."""
    assert post_action(env, UNKNOWN_ID, "preview").status_code == 404


# ---- approval invalidation (A5) -------------------------------------------------------


def test_changing_the_slot_after_approval_requires_a_new_preview(env: Env) -> None:
    """TT-AC7-N6 (A5)."""
    template_id = usable_template(env)
    batch_id = create_batch(env, template_id, people(2)).json()["id"]
    approve_preview(env, batch_id)
    set_slot(env, template_id, 1.1, 1.7)
    confirm_slot(env, template_id)
    assert get_batch(env, batch_id)["preview"]["approved"] is False
    response = start(env, batch_id)
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_APPROVED"
    assert env.queue.rows == []


def test_a_new_preview_and_approval_after_the_change_allows_start(env: Env) -> None:
    """TT-AC7-E6 (A5)."""
    template_id = usable_template(env)
    batch_id = create_batch(env, template_id, people(2)).json()["id"]
    approve_preview(env, batch_id)
    set_slot(env, template_id, 1.1, 1.7)
    confirm_slot(env, template_id)
    approve_preview(env, batch_id)
    assert start(env, batch_id).status_code == 200
    assert audit_actions(env).count("PREVIEW_APPROVED") == 2


def test_changing_the_column_mapping_after_approval_invalidates_it(env: Env) -> None:
    """TT-AC7-N8 (A5)."""
    batch_id = new_batch(env, [["Asha", "A1", "Aasha"]], header=["Name", "ID", "Spoken"])
    approve_preview(env, batch_id)
    response = env.client.put(
        f"/batches/{batch_id}/mapping",
        json={"name_column": "Name", "id_column": "ID", "spoken_name_column": "Spoken"},
        headers=env.csrf,
    )
    assert response.status_code == 200
    assert response.json()["preview"]["approved"] is False
    assert start(env, batch_id).status_code == 409


def test_a_valid_mapping_change_revalidates_the_rows(env: Env, db: Engine) -> None:
    """TT-AC2-P4: using another column as the ID removes the duplicate."""
    rows = [["Asha", "X", "1"], ["Bina", "X", "2"]]
    batch_id = new_batch(env, rows, header=["Name", "ID", "Alt"])
    assert row_status(db, batch_id) == {2: "QUEUED", 3: "SKIPPED"}
    response = env.client.put(
        f"/batches/{batch_id}/mapping",
        json={"name_column": "Name", "id_column": "Alt"},
        headers=env.csrf,
    )
    assert response.status_code == 200
    assert response.json()["report"]["skipped_rows"] == 0
    assert row_status(db, batch_id) == {2: "QUEUED", 3: "QUEUED"}


def test_an_invalid_mapping_change_is_refused_and_changes_nothing(env: Env, db: Engine) -> None:
    """TT-AC2-N6."""
    batch_id = new_batch(
        env, [["Asha", "1"], ["Bina", "2"]], header=["Name", "Code"], id_column="Code"
    )
    response = env.client.put(
        f"/batches/{batch_id}/mapping",
        json={"name_column": "Name", "id_column": "Name"},
        headers=env.csrf,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "COLUMN_NOT_FOUND"
    assert row_status(db, batch_id) == {2: "QUEUED", 3: "QUEUED"}


def test_switching_the_template_after_approval_invalidates_it(env: Env) -> None:
    """TT-AC7-N7 (A5)."""
    first = usable_template(env)
    second = usable_template(env)
    batch_id = create_batch(env, first, people(2)).json()["id"]
    approve_preview(env, batch_id)
    response = env.client.put(
        f"/batches/{batch_id}/template", json={"template_id": second}, headers=env.csrf
    )
    assert response.status_code == 200
    assert response.json()["template_id"] == second
    assert response.json()["preview"]["approved"] is False
    assert start(env, batch_id).status_code == 409


def test_switching_to_an_unusable_template_is_refused(env: Env) -> None:
    """TT-AC7-N7."""
    from tests.integration.api.helpers import new_template

    batch_id = new_batch(env)
    unusable = new_template(env)
    response = env.client.put(
        f"/batches/{batch_id}/template", json={"template_id": unusable}, headers=env.csrf
    )
    assert response.status_code == 409


def test_a_started_batch_cannot_change_template_or_mapping(env: Env) -> None:
    """TT-AC18-E6 (content lock): nothing about a running batch can be re-targeted."""
    template_id = usable_template(env)
    batch_id = create_batch(env, template_id, people(2)).json()["id"]
    approve_preview(env, batch_id)
    start(env, batch_id)
    mapping = env.client.put(
        f"/batches/{batch_id}/mapping",
        json={"name_column": "Name", "id_column": "ID"},
        headers=env.csrf,
    )
    assert mapping.status_code == 409
    assert mapping.json()["code"] == "INVALID_STATE"


# ---- start: queueing, folders, idempotency --------------------------------------------


def test_start_queues_every_valid_row_exactly_once_and_skips_invalid_rows(
    env: Env, db: Engine
) -> None:
    """TT-AC3-N7, AC12-P1."""
    rows = [["Asha", "A1"], ["", "B2"], ["Chand", "C3"], ["Dev", "A1"]]
    batch_id = new_batch(env, rows)
    approve_preview(env, batch_id)
    response = start(env, batch_id)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["queued_rows"] == 2
    ids = row_ids(db, batch_id)
    assert sorted(row_id for _, row_id in env.queue.rows) == sorted([ids[2], ids[4]])
    assert {bid for bid, _ in env.queue.rows} == {UUID(batch_id)}
    assert row_status(db, batch_id)[3] == "SKIPPED"
    assert row_status(db, batch_id)[5] == "SKIPPED"


def test_default_folder_name_is_date_and_valid_row_count(env: Env) -> None:
    """TT-AC11-P1: the date comes from the clock at start time."""
    batch_id = new_batch(env, [["Asha", "A1"], ["", "B2"], ["Chand", "C3"]])
    approve_preview(env, batch_id)
    env.advance(days=1)
    assert start(env, batch_id).json()["folder_name"] == "2026-10-19-2"


def test_custom_folder_name_is_used(env: Env) -> None:
    """TT-AC11-P2."""
    batch_id = new_batch(env)
    approve_preview(env, batch_id)
    assert (
        start(env, batch_id, folder="Ward 12 Campaign").json()["folder_name"] == "Ward 12 Campaign"
    )


@pytest.mark.parametrize("folder", ["", "   ", "\t"])
def test_empty_custom_folder_name_falls_back_to_the_default(env: Env, folder: str) -> None:
    """TT-AC11-E12, E13 (B4)."""
    batch_id = new_batch(env, people(3))
    approve_preview(env, batch_id)
    assert start(env, batch_id, folder=folder).json()["folder_name"] == "2026-10-18-3"


@pytest.mark.parametrize(
    "folder", ["../../etc", "/abs/path", "a/../b", "..", "bad<name", "CON", "trailing.", "x" * 300]
)
def test_traversal_and_illegal_folder_names_are_refused_before_anything_is_queued(
    env: Env, folder: str
) -> None:
    """TT-AC11-N1, N2, N3: INVALID_FOLDER_NAME; the batch stays a draft."""
    batch_id = new_batch(env)
    approve_preview(env, batch_id)
    response = start(env, batch_id, folder=folder)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_FOLDER_NAME"
    assert env.queue.rows == []
    assert get_batch(env, batch_id)["status"] == "DRAFT"


def test_an_existing_folder_name_gets_a_numeric_suffix(env: Env) -> None:
    """TT-AC11-P3, E1: never reuse the folder of another batch."""
    first = new_batch(env, people(3))
    approve_preview(env, first)
    assert start(env, first, key="k-first").json()["folder_name"] == "2026-10-18-3"
    second = new_batch(env, people(3))
    approve_preview(env, second)
    assert start(env, second, key="k-second").json()["folder_name"] == "2026-10-18-3-2"
    third = new_batch(env, people(3))
    approve_preview(env, third)
    assert start(env, third, key="k-third").json()["folder_name"] == "2026-10-18-3-3"


def test_a_folder_that_already_exists_in_storage_gets_a_suffix_and_stays_untouched(
    env: Env,
) -> None:
    """TT-AC11-P3 (R6.2): no batch owns the folder, but files are already there."""
    env.storage.files["2026-10-18-3/stray.txt"] = b"do not touch"
    batch_id = new_batch(env, people(3))
    approve_preview(env, batch_id)
    assert start(env, batch_id).json()["folder_name"] == "2026-10-18-3-2"
    assert env.storage.files["2026-10-18-3/stray.txt"] == b"do not touch"


def test_an_existing_custom_folder_in_storage_also_gets_a_suffix(env: Env) -> None:
    """TT-AC11-P3 (R6.2)."""
    env.storage.files["Ward 12/old.mp4"] = b"old"
    batch_id = new_batch(env, people(2))
    approve_preview(env, batch_id)
    assert start(env, batch_id, folder="Ward 12").json()["folder_name"] == "Ward 12-2"
    assert env.storage.files["Ward 12/old.mp4"] == b"old"


def test_same_custom_folder_used_twice_gets_a_suffix(env: Env) -> None:
    """TT-AC11-P3."""
    names = []
    for index in range(2):
        batch_id = new_batch(env)
        approve_preview(env, batch_id)
        names.append(start(env, batch_id, key=f"k{index}", folder="Campaign").json()["folder_name"])
    assert names == ["Campaign", "Campaign-2"]


def test_start_requires_an_idempotency_key(env: Env) -> None:
    """B11."""
    batch_id = new_batch(env)
    approve_preview(env, batch_id)
    response = start(env, batch_id, key=None)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert env.queue.rows == []


def test_repeating_start_with_the_same_key_returns_the_same_result_without_new_jobs(
    env: Env,
) -> None:
    """TT-AC13-P5 (B11)."""
    batch_id = new_batch(env, people(3))
    approve_preview(env, batch_id)
    first = start(env, batch_id, key="same")
    second = start(env, batch_id, key="same")
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(env.queue.rows) == 3
    assert audit_actions(env).count("BATCH_STARTED") == 1


def test_start_on_an_already_started_batch_with_another_key_is_a_no_op(env: Env) -> None:
    """TT-AC13-E10 (B11): current state is returned, nothing is queued again."""
    batch_id = new_batch(env, people(3))
    approve_preview(env, batch_id)
    start(env, batch_id, key="one")
    again = start(env, batch_id, key="two")
    assert again.status_code == 200
    assert again.json()["status"] == "RUNNING"
    assert len(env.queue.rows) == 3


def test_a_key_reused_on_another_batch_is_409_idempotency_key_conflict(env: Env) -> None:
    """C2."""
    first = new_batch(env, people(2))
    second = new_batch(env, people(2))
    approve_preview(env, first)
    approve_preview(env, second)
    assert start(env, first, key="shared").status_code == 200
    response = start(env, second, key="shared")
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert get_batch(env, second)["status"] == "DRAFT"
    assert len(env.queue.rows) == 2


def test_two_simultaneous_starts_with_the_same_key_queue_each_row_once(env: Env) -> None:
    """TT-AC13-E11."""
    batch_id = new_batch(env, people(4))
    approve_preview(env, batch_id)
    results: list[int] = []

    def worker() -> None:
        client = env.client_from("10.0.0.9")
        client.cookies.update(env.client.cookies)
        response = client.post(
            f"/batches/{batch_id}/start",
            json={},
            headers={**env.csrf, "Idempotency-Key": "race"},
        )
        results.append(response.status_code)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [200, 200]
    assert len(env.queue.rows) == 4
    assert len({row_id for _, row_id in env.queue.rows}) == 4


def test_start_for_unknown_batch_is_404(env: Env) -> None:
    """TT-AC13-N4."""
    assert start(env, UNKNOWN_ID).status_code == 404


def test_actions_need_the_csrf_token(env: Env) -> None:
    """TT-AC16-N2."""
    batch_id = new_batch(env)
    for path in (
        "preview",
        "preview/approve",
        "start",
        "pause",
        "resume",
        "cancel",
        "retry-failed",
    ):
        response = env.client.post(f"/batches/{batch_id}/{path}")
        assert response.status_code == 403, path
        assert response.json()["code"] == "CSRF_FAILED"
    assert env.client.delete(f"/batches/{batch_id}").status_code == 403
