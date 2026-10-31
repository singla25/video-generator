"""Batch deletion, retention and privacy of logs/audit (AC17, A8, B12, C5)."""

from __future__ import annotations

import io
import logging
from datetime import timedelta

import pytest
from sqlalchemy import Engine, text

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from tests.integration.api.batch_helpers import (
    approve_preview,
    create_batch,
    finish_row,
    get_batch,
    new_batch,
    people,
    post_action,
    running_batch,
    set_batch,
    start,
    table_count,
    usable_template,
)
from tests.integration.api.conftest import Env, EnvFactory
from vidgen.infrastructure.db.models import Batch, BatchRow

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
DAY = timedelta(days=1)
CANARY_ROW = [CANARY_NAME.replace("-", " "), CANARY_ID]


def run_retention(env: Env) -> int:
    """Run the retention job (a service function, not an endpoint) and return deleted batches."""
    return int(env.app.state.container.batches.run_retention())


def audit_actions(env: Env) -> list[str]:
    """Audit actions, oldest first."""
    return [e["action"] for e in env.client.get("/audit").json()["entries"]]


# ---- deletion -------------------------------------------------------------------------


def test_deleting_a_batch_removes_rows_and_stored_files(env: Env, db: Engine) -> None:
    """TT-AC17-P5: rows, sheet, preview and outputs go; the template's files stay."""
    template_id = usable_template(env)
    template_files = set(env.storage.files)
    batch_id = create_batch(env, template_id, [CANARY_ROW, ["Asha", "A2"]]).json()["id"]
    approve_preview(env, batch_id)
    start(env, batch_id)
    key = env.storage.write("2026-10-18-2/A2.mp4", io.BytesIO(b"OUT"))
    finish_row(db, batch_id, 3, at=env.clock.now(), output_key=key)
    assert set(env.storage.files) > template_files
    response = env.client.delete(f"/batches/{batch_id}", headers=env.csrf)
    assert response.status_code == 204
    assert table_count(db, Batch) == 0
    assert table_count(db, BatchRow) == 0
    assert env.client.get(f"/batches/{batch_id}").status_code == 404
    assert set(env.storage.files) == template_files


def test_no_personal_data_survives_deletion_anywhere_in_the_database(env: Env, db: Engine) -> None:
    """TT-AC17-P5: a full-database text scan after deletion."""
    batch_id = running_batch(env, [CANARY_ROW])
    env.client.delete(f"/batches/{batch_id}", headers=env.csrf)
    with db.connect() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        dump = ""
        for name in tables:
            dump += "\n".join(conn.execute(text(f'SELECT t::text FROM "{name}" t')).scalars())  # noqa: S608
    assert "Canary" not in dump
    assert "CANARY1" not in dump


def test_audit_entries_survive_deletion_without_personal_data(env: Env) -> None:
    """TT-AC17-P7."""
    batch_id = running_batch(env, [CANARY_ROW])
    env.client.delete(f"/batches/{batch_id}", headers=env.csrf)
    actions = audit_actions(env)
    assert "BATCH_STARTED" in actions
    assert "BATCH_DELETED" in actions
    log = env.client.get("/audit").text
    assert "Canary" not in log
    assert "CANARY1" not in log


def test_deleting_an_unknown_batch_is_404(env: Env) -> None:
    """TT-AC17-N5."""
    response = env.client.delete(f"/batches/{UNKNOWN_ID}", headers=env.csrf)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_deleting_without_a_session_is_401(env: Env) -> None:
    """TT-AC17-N5."""
    batch_id = new_batch(env)
    stranger = env.client_from("10.4.4.4")
    assert stranger.delete(f"/batches/{batch_id}").status_code == 401


def test_a_running_batch_can_be_deleted_and_its_queued_jobs_become_harmless(env: Env) -> None:
    """TT-AC17-E8: the batch is gone; later worker calls find nothing."""
    batch_id = running_batch(env, people(3))
    assert env.client.delete(f"/batches/{batch_id}", headers=env.csrf).status_code == 204
    assert env.client.get(f"/batches/{batch_id}/status").status_code == 404


def test_other_batches_are_untouched_by_a_deletion(env: Env, db: Engine) -> None:
    """TT-AC17-P5."""
    template_id = usable_template(env)
    keep = create_batch(env, template_id, people(2)).json()["id"]
    drop = create_batch(env, template_id, people(3)).json()["id"]
    env.client.delete(f"/batches/{drop}", headers=env.csrf)
    assert get_batch(env, keep)["id"] == keep
    assert table_count(db, BatchRow) == 2


def test_deleted_batch_drops_the_preview_file_too(env: Env) -> None:
    """TT-AC7-E5."""
    batch_id = new_batch(env)
    approve_preview(env, batch_id)
    assert any(k.startswith("previews/") for k in env.storage.files)
    env.client.delete(f"/batches/{batch_id}", headers=env.csrf)
    assert not any(k.startswith("previews/") for k in env.storage.files)


# ---- retention ------------------------------------------------------------------------


def finished_batch(env: Env, db: Engine, *, age: timedelta, status: str = "COMPLETED") -> str:
    """A started batch whose finish time lies ``age`` in the past."""
    batch_id = _fresh_running(env)
    set_batch(db, batch_id, status=status, finished_at=env.clock.now() - age)
    return batch_id


def _fresh_running(env: Env) -> str:
    """Create, approve and start a one-row batch with a unique idempotency key."""
    batch_id = new_batch(env, people(1))
    approve_preview(env, batch_id)
    assert start(env, batch_id, key=f"k-{batch_id}").status_code == 200
    return batch_id


def test_finished_batches_older_than_the_retention_period_are_deleted(env: Env, db: Engine) -> None:
    """TT-AC17-P6 (B12): default 30 days, counted from the finish time."""
    old = finished_batch(env, db, age=31 * DAY)
    recent = finished_batch(env, db, age=29 * DAY)
    assert run_retention(env) == 1
    assert env.client.get(f"/batches/{old}").status_code == 404
    assert env.client.get(f"/batches/{recent}").status_code == 200


def test_retention_boundary_is_strictly_older_than_n_days(env: Env, db: Engine) -> None:
    """TT-AC17-E5: exactly 30 days is kept, 30 days and 1 second is deleted."""
    exact = finished_batch(env, db, age=30 * DAY)
    over = finished_batch(env, db, age=30 * DAY + timedelta(seconds=1))
    assert run_retention(env) == 1
    assert env.client.get(f"/batches/{exact}").status_code == 200
    assert env.client.get(f"/batches/{over}").status_code == 404


def test_cancelled_batches_count_from_the_cancel_time(env: Env, db: Engine) -> None:
    """TT-AC17-P9 (B12)."""
    batch_id = finished_batch(env, db, age=31 * DAY, status="CANCELLED")
    assert run_retention(env) == 1
    assert env.client.get(f"/batches/{batch_id}").status_code == 404


@pytest.mark.parametrize("status", ["RUNNING", "PAUSED"])
def test_unfinished_batches_are_never_deleted_however_old(
    env: Env, db: Engine, status: str
) -> None:
    """TT-AC17-N7 (A8)."""
    batch_id = _fresh_running(env)
    set_batch(db, batch_id, status=status, started_at=env.clock.now() - 90 * DAY)
    env.advance(days=90)
    assert run_retention(env) == 0
    assert env.client.get(f"/batches/{batch_id}").status_code == 200


def test_never_started_drafts_are_deleted_n_days_after_creation(env: Env, db: Engine) -> None:
    """TT-AC17-P8 (B12)."""
    draft = new_batch(env, people(2))
    env.advance(days=30, seconds=1)
    assert run_retention(env) == 1
    assert env.client.get(f"/batches/{draft}").status_code == 404


def test_young_drafts_are_kept(env: Env) -> None:
    """TT-AC17-N8."""
    draft = new_batch(env, people(2))
    env.advance(days=29)
    assert run_retention(env) == 0
    assert env.client.get(f"/batches/{draft}").status_code == 200


def test_retention_period_comes_from_settings(make_env: EnvFactory, db: Engine) -> None:
    """TT-AC17-P6."""
    env = make_env(retention_days=7)
    draft = new_batch(env, people(1))
    env.advance(days=8)
    assert run_retention(env) == 1
    assert env.client.get(f"/batches/{draft}").status_code == 404


def test_retention_removes_files_and_audits_as_the_system(env: Env, db: Engine) -> None:
    """TT-AC17-P6, P7."""
    batch_id = finished_batch(env, db, age=31 * DAY)
    assert run_retention(env) == 1
    assert table_count(db, BatchRow) == 0
    entry = env.client.get("/audit", params={"action": "BATCH_DELETED"}).json()["entries"][-1]
    assert entry["actor"] == "system"
    assert entry["details"]["batch_id"] == batch_id
    assert entry["details"]["reason"] == "retention"


def test_retention_with_nothing_to_do_is_harmless(env: Env) -> None:
    """TT-AC17-E5."""
    assert run_retention(env) == 0


# ---- privacy of logs and errors -------------------------------------------------------


# The HTTP test client logs every request URL at INFO (httpx2 under the TestClient, httpx
# otherwise), query strings included. That is the harness talking, not the app, so it is left out.
TEST_CLIENT_LOGGERS = ("httpx", "httpx2", "httpcore")


def app_log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Every captured log record except the test client's own request log, fully formatted."""
    return "\n".join(
        caplog.handler.format(record)
        for record in caplog.records
        if record.name.split(".")[0] not in TEST_CLIENT_LOGGERS
    )


def test_no_personal_data_in_logs_during_the_whole_batch_flow(
    env: Env, db: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """TT-AC17-P4 (C5)."""
    with caplog.at_level(logging.DEBUG):
        batch_id = running_batch(env, [CANARY_ROW, ["", CANARY_ID + "X"], ["Asha", "A9"]])
        env.client.get(f"/batches/{batch_id}/rows", params={"search": "Canary"})
        env.client.get(f"/batches/{batch_id}/failures.csv")
        post_action(env, batch_id, "pause")
        post_action(env, batch_id, "cancel")
        env.client.delete(f"/batches/{batch_id}", headers=env.csrf)
    logged = app_log_text(caplog)
    assert "Canary" not in logged
    assert "CANARY1" not in logged


def test_error_bodies_never_contain_personal_data(env: Env) -> None:
    """TT-AC17-N4."""
    template_id = usable_template(env)
    response = create_batch(env, template_id, [CANARY_ROW], name_column="Nope-" + CANARY_NAME)
    assert response.status_code == 422
    assert "Canary" not in response.text
    batch_id = create_batch(env, template_id, [CANARY_ROW]).json()["id"]
    for path in ("preview/approve", "resume"):
        assert "Canary" not in post_action(env, batch_id, path).text


def test_audit_details_for_batches_contain_ids_and_counts_only(env: Env) -> None:
    """C4, C5."""
    batch_id = running_batch(env, [CANARY_ROW, ["Asha", "A2"]])
    entries = env.client.get("/audit").json()["entries"]
    text_dump = str(entries)
    assert "Canary" not in text_dump
    assert "CANARY1" not in text_dump
    created = next(e for e in entries if e["action"] == "BATCH_CREATED")
    assert created["details"]["batch_id"] == batch_id
    assert created["details"]["total_rows"] == 2
