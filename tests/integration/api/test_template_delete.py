"""Template deletion: 204 when unused, 409 TEMPLATE_IN_USE while any batch uses it (DD-37)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME, pdf_bytes, png_bytes
from tests.integration.api.batch_helpers import (
    new_batch,
    people,
    set_batch,
    table_count,
    usable_template,
)
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.helpers import new_template, upload_consent
from vidgen.infrastructure.db.models import ConsentRecord, Template

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def stored_keys(db: Engine, template_id: str) -> tuple[str, list[str]]:
    """The template video key and every consent file key, as the database records them."""
    template = UUID(template_id)
    with Session(db) as session:
        video = session.execute(
            select(Template.video_key).where(Template.id == template)
        ).scalar_one()
        consents = list(
            session.scalars(
                select(ConsentRecord.file_key).where(ConsentRecord.template_id == template)
            )
        )
    return video, consents


def delete_template(env: Env, template_id: str) -> Any:
    """DELETE /templates/{id} with the CSRF header."""
    return env.client.delete(f"/templates/{template_id}", headers=env.csrf)


def template_audit(env: Env, action: str) -> list[dict[str, Any]]:
    """Audit entries of one action, oldest first."""
    response = env.client.get("/audit", params={"action": action})
    assert response.status_code == 200, response.text
    entries: list[dict[str, Any]] = response.json()["entries"]
    return entries


# ---- positive -------------------------------------------------------------------------


def test_deleting_an_unused_template_returns_204_and_it_is_gone(env: Env, db: Engine) -> None:
    """DD-37 P1: 204, then GET is 404 and the list is empty."""
    template_id = usable_template(env)
    response = delete_template(env, template_id)
    assert response.status_code == 204
    assert env.client.get(f"/templates/{template_id}").status_code == 404
    assert env.client.get("/templates").json()["templates"] == []
    assert table_count(db, Template) == 0


def test_deleting_removes_the_stored_video_and_consent_file(env: Env, db: Engine) -> None:
    """DD-37 P2: both storage keys are deleted from storage."""
    template_id = usable_template(env)
    video, consents = stored_keys(db, template_id)
    assert video in env.storage.files
    assert consents and all(key in env.storage.files for key in consents)
    assert delete_template(env, template_id).status_code == 204
    assert video not in env.storage.files
    assert all(key not in env.storage.files for key in consents)
    assert env.storage.files == {}


def test_deleting_removes_every_consent_record_and_its_file(env: Env, db: Engine) -> None:
    """DD-37 P3: a replaced consent keeps history in the database; delete takes all of it."""
    template_id = new_template(env)
    assert upload_consent(env, template_id, content=pdf_bytes()).status_code == 200
    assert (
        upload_consent(env, template_id, content=png_bytes(), filename="c.png").status_code == 200
    )
    _, consents = stored_keys(db, template_id)
    assert len(consents) == 2
    assert delete_template(env, template_id).status_code == 204
    assert table_count(db, ConsentRecord) == 0
    assert all(key not in env.storage.files for key in consents)


def test_deleting_one_template_leaves_another_templates_files_alone(env: Env, db: Engine) -> None:
    """DD-37 P4: only the deleted template's files go."""
    doomed = usable_template(env)
    kept = usable_template(env)
    kept_video, kept_consents = stored_keys(db, kept)
    assert delete_template(env, doomed).status_code == 204
    assert kept_video in env.storage.files
    assert all(key in env.storage.files for key in kept_consents)
    assert env.client.get(f"/templates/{kept}").status_code == 200


def test_delete_writes_one_audit_entry_with_the_id_and_no_names(env: Env) -> None:
    """DD-37 P5: TEMPLATE_DELETED names the template id; the name and file name never appear."""
    template_id = usable_template(env, original_name=CANARY_NAME)
    assert delete_template(env, template_id).status_code == 204
    entries = template_audit(env, "TEMPLATE_DELETED")
    assert len(entries) == 1
    assert entries[0]["details"]["template_id"] == template_id
    serialised = json.dumps(entries[0])
    assert CANARY_NAME not in serialised
    assert CANARY_ID not in serialised


def test_template_is_deletable_after_its_only_batch_was_deleted(env: Env) -> None:
    """DD-37 P6: deleting the last batch that uses a template frees the template."""
    template_id = usable_template(env)
    batch_id = new_batch(env, people(2), template_id=template_id)
    assert delete_template(env, template_id).status_code == 409
    assert env.client.delete(f"/batches/{batch_id}", headers=env.csrf).status_code == 204
    assert delete_template(env, template_id).status_code == 204


# ---- negative -------------------------------------------------------------------------


def test_template_used_by_a_draft_batch_is_409_and_kept(env: Env, db: Engine) -> None:
    """DD-37 N1: a DRAFT batch counts as a use."""
    template_id = usable_template(env)
    new_batch(env, people(2), template_id=template_id)
    response = delete_template(env, template_id)
    assert response.status_code == 409
    assert response.json() == {
        "code": "TEMPLATE_IN_USE",
        "message": "This template is used by 1 batch. Delete those batches first.",
    }
    assert env.client.get(f"/templates/{template_id}").status_code == 200
    assert len(stored_keys(db, template_id)[1]) == 1
    assert template_audit(env, "TEMPLATE_DELETED") == []


def test_template_used_by_a_completed_batch_is_409_and_kept(env: Env, db: Engine) -> None:
    """DD-37 N2: a COMPLETED batch counts as a use."""
    template_id = usable_template(env)
    batch_id = new_batch(env, people(2), template_id=template_id)
    set_batch(db, batch_id, status="COMPLETED")
    response = delete_template(env, template_id)
    assert response.status_code == 409
    assert response.json()["code"] == "TEMPLATE_IN_USE"
    assert env.client.get(f"/templates/{template_id}").status_code == 200


@pytest.mark.parametrize("status", ["RUNNING", "PAUSED", "CANCELLED"])
def test_template_used_by_a_batch_in_any_other_status_is_409(
    env: Env, db: Engine, status: str
) -> None:
    """DD-37 N3: every batch status blocks the delete."""
    template_id = usable_template(env)
    batch_id = new_batch(env, people(2), template_id=template_id)
    set_batch(db, batch_id, status=status)
    response = delete_template(env, template_id)
    assert response.status_code == 409
    assert response.json()["code"] == "TEMPLATE_IN_USE"
    assert env.client.get(f"/templates/{template_id}").status_code == 200


@pytest.mark.parametrize(
    ("statuses", "wording"),
    [
        (["DRAFT"], "1 batch"),
        (["DRAFT", "COMPLETED", "RUNNING"], "3 batches"),
    ],
)
def test_conflict_message_counts_every_batch_with_the_right_plural(
    env: Env, db: Engine, statuses: list[str], wording: str
) -> None:
    """DD-37 N4: N counts batches in any status; 'batch' for one, 'batches' otherwise."""
    template_id = usable_template(env)
    for status in statuses:
        batch_id = new_batch(env, people(2), template_id=template_id)
        set_batch(db, batch_id, status=status)
    response = delete_template(env, template_id)
    assert response.status_code == 409
    assert response.json() == {
        "code": "TEMPLATE_IN_USE",
        "message": f"This template is used by {wording}. Delete those batches first.",
    }


def test_only_batches_of_this_template_are_counted(env: Env) -> None:
    """DD-37 N5: batches that use another template do not count."""
    busy = usable_template(env)
    idle = usable_template(env)
    new_batch(env, people(2), template_id=busy)
    new_batch(env, people(2), template_id=busy)
    new_batch(env, people(2), template_id=idle)
    busy_response = delete_template(env, busy)
    assert busy_response.status_code == 409
    assert busy_response.json()["message"] == (
        "This template is used by 2 batches. Delete those batches first."
    )
    idle_response = delete_template(env, idle)
    assert idle_response.status_code == 409
    assert idle_response.json()["message"] == (
        "This template is used by 1 batch. Delete those batches first."
    )


def test_unknown_template_is_404(env: Env) -> None:
    """DD-37 N6."""
    response = delete_template(env, UNKNOWN_ID)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_deleting_twice_is_404_the_second_time(env: Env) -> None:
    """DD-37 E1: a repeated delete is not a success twice."""
    template_id = usable_template(env)
    assert delete_template(env, template_id).status_code == 204
    assert delete_template(env, template_id).status_code == 404


def test_delete_without_a_session_is_401_and_removes_nothing(
    env: Env, make_env: EnvFactory, db: Engine
) -> None:
    """DD-37 N7: like every other route, no session means 401 before anything happens."""
    template_id = usable_template(env)
    video, _ = stored_keys(db, template_id)
    anon = make_env(login=False)
    response = anon.client.delete(f"/templates/{template_id}")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert table_count(db, Template) == 1
    assert video in env.storage.files


def test_delete_without_the_csrf_token_is_refused(env: Env, db: Engine) -> None:
    """DD-37 N8: the router's CSRF rule applies to the new route too."""
    template_id = usable_template(env)
    response = env.client.delete(f"/templates/{template_id}")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"
    assert table_count(db, Template) == 1
