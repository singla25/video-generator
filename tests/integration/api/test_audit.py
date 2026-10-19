"""Audit log API and content (C4, C5, AC17)."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME, pdf_bytes
from tests.integration.api.conftest import PASSWORD, Env
from tests.integration.api.helpers import (
    audit_actions,
    confirm_slot,
    krishan_at,
    new_template,
    set_slot,
    upload_consent,
    upload_template,
)


def entries(env: Env, **params: str) -> list[dict[str, object]]:
    """GET /audit entries, oldest first."""
    response = env.client.get("/audit", params=params)
    assert response.status_code == 200
    result: list[dict[str, object]] = response.json()["entries"]
    return result


def run_full_flow(env: Env) -> str:
    """Upload, consent, analyse, manual slot, confirm; return the template id."""
    env.stt.words = [krishan_at(1.0)]
    template_id = new_template(env, filename=f"{CANARY_NAME}.mp4")
    upload_consent(env, template_id, content=pdf_bytes(), filename=f"{CANARY_ID}.pdf")
    env.client.post(f"/templates/{template_id}/analyse", headers=env.csrf)
    set_slot(env, template_id, 1.0, 1.6)
    confirm_slot(env, template_id)
    return template_id


def test_flow_is_audited_in_order(env: Env) -> None:
    """TT-AC5-P3, AC6, C4: login, upload, consent, analysis, slot, confirmation."""
    run_full_flow(env)
    assert audit_actions(env) == [
        "LOGIN_SUCCEEDED",
        "TEMPLATE_UPLOADED",
        "CONSENT_UPLOADED",
        "TEMPLATE_ANALYSED",
        "SLOT_SET",
        "SLOT_CONFIRMED",
    ]


def test_each_entry_has_actor_time_action_and_details(env: Env) -> None:
    """C4: actor 'admin', ISO time from the injected clock, details object."""
    env.clock.advance(minutes=5)
    template_id = new_template(env)
    upload = entries(env, action="TEMPLATE_UPLOADED")[0]
    assert upload["actor"] == "admin"
    assert str(upload["at"]).startswith("2026-10-18T09:05")
    assert isinstance(upload["details"], dict)
    assert upload["details"]["template_id"] == template_id


def test_failed_and_successful_logins_are_audited(anon: Env) -> None:
    """C4: failed logins use the actor 'anonymous' and never store the password."""
    anon.login("not-the-password-CANARY")
    anon.login(PASSWORD)
    rows = entries(anon)
    assert [(r["action"], r["actor"]) for r in rows] == [
        ("LOGIN_FAILED", "anonymous"),
        ("LOGIN_SUCCEEDED", "admin"),
    ]
    assert "not-the-password-CANARY" not in str(rows)


def test_logout_event_is_recorded(env: Env) -> None:
    """C4."""
    env.client.post("/auth/logout", headers=env.csrf)
    # the session is closed, so read the log with a fresh login
    assert env.login().status_code == 200
    assert "LOGOUT" in audit_actions(env)


def test_action_filter_returns_only_matching_entries(env: Env) -> None:
    """C4."""
    run_full_flow(env)
    only = entries(env, action="SLOT_SET")
    assert [e["action"] for e in only] == ["SLOT_SET"]


def test_audit_entries_contain_no_personal_data(env: Env, db: Engine) -> None:
    """TT-AC17-P7/E12 (C5): canary names, IDs and file names never appear in the log."""
    run_full_flow(env)
    api_text = env.client.get("/audit").text
    with db.connect() as conn:
        db_text = "\n".join(conn.execute(text("SELECT t::text FROM audit_log t")).scalars())
    for secret in (CANARY_NAME, CANARY_ID, "Canary", "CANARY1"):
        assert secret not in api_text
        assert secret not in db_text


def test_audit_survives_everything_the_flow_does(env: Env, db: Engine) -> None:
    """C4: entries are persisted in the database, not kept in memory."""
    run_full_flow(env)
    with db.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
    assert count == 6


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "POST"])
def test_audit_log_cannot_be_modified_through_the_api(env: Env, method: str) -> None:
    """TT-AC17-N6: no write routes."""
    run_full_flow(env)
    before = len(entries(env))
    response = env.client.request(method, "/audit", json={}, headers=env.csrf)
    assert response.status_code in (404, 405)
    response = env.client.request(method, "/audit/1", json={}, headers=env.csrf)
    assert response.status_code in (404, 405)
    assert len(entries(env)) == before


def test_audit_requires_a_session(anon: Env) -> None:
    """TT-AC16-P6."""
    assert anon.client.get("/audit").status_code == 401


def test_rejected_uploads_are_not_audited_as_uploads(env: Env) -> None:
    """C4: only accepted actions create TEMPLATE_UPLOADED."""
    upload_template(env, content=b"not a video")
    assert "TEMPLATE_UPLOADED" not in audit_actions(env)
