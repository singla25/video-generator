"""Template upload and consent gate (AC1 API part, AC5, C1, C5)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from tests.fixtures.doubles import (
    CANARY_NAME,
    UNSUPPORTED_VIDEO,
    VALID_VIDEO,
    jpeg_bytes,
    pdf_bytes,
    png_bytes,
)
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.helpers import (
    audit_actions,
    confirm_slot,
    get_template,
    new_template,
    set_slot,
    upload_consent,
    upload_template,
)
from vidgen.domain.codes import FailureCode, plain_message

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def template_count(db: Engine) -> int:
    """Rows in the templates table."""
    with db.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM templates")).scalar_one())


# ---- upload: positive -----------------------------------------------------------------


def test_valid_video_creates_a_template_with_probe_facts(env: Env) -> None:
    """TT-AC1-P1 (API): 201, stored once, unusable until consent and slot."""
    response = upload_template(env)
    assert response.status_code == 201
    body = response.json()
    assert body["original_name"] == "Krishan"
    assert (body["duration_s"], body["width"], body["height"]) == (4.0, 320, 240)
    assert body["usable"] is False
    assert body["consent_confirmed"] is False
    assert body["slot"] is None
    assert body["slot_confirmed"] is False
    assert len(env.storage.files) == 1
    assert len(env.probe.calls) == 1


def test_created_template_can_be_read_and_listed(env: Env) -> None:
    """TT-AC1-P1."""
    template_id = new_template(env)
    assert get_template(env, template_id)["id"] == template_id
    listing = env.client.get("/templates").json()
    assert [t["id"] for t in listing["templates"]] == [template_id]


def test_two_uploads_give_two_independent_templates(env: Env) -> None:
    """TT-AC1-E10."""
    first, second = new_template(env), new_template(env)
    assert first != second
    assert len(env.storage.files) == 2


# ---- upload: negative -----------------------------------------------------------------


def test_unsupported_video_is_422_and_nothing_is_kept(env: Env, db: Engine) -> None:
    """TT-AC1-N1."""
    response = upload_template(env, content=UNSUPPORTED_VIDEO)
    assert response.status_code == 422
    assert response.json() == {
        "code": "UNSUPPORTED_VIDEO",
        "message": plain_message(FailureCode.UNSUPPORTED_VIDEO),
    }
    assert env.storage.files == {}
    assert template_count(db) == 0


@pytest.mark.parametrize("content", [b"", b"just text, not a video"])
def test_corrupt_or_empty_video_is_422_corrupt(env: Env, db: Engine, content: bytes) -> None:
    """TT-AC1-N3, E2."""
    response = upload_template(env, content=content)
    assert response.status_code == 422
    assert response.json()["code"] == "CORRUPT_VIDEO"
    assert env.storage.files == {}
    assert template_count(db) == 0


def test_request_without_a_file_is_a_validation_error(env: Env) -> None:
    """TT-AC1-N8."""
    response = env.client.post("/templates", data={"original_name": "Krishan"}, headers=env.csrf)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("original_name", [None, "", "   "])
def test_missing_or_blank_original_name_is_rejected(
    env: Env, db: Engine, original_name: str | None
) -> None:
    """The name to replace is part of the template; without it analysis cannot work."""
    response = upload_template(env, original_name=original_name)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert env.storage.files == {}
    assert template_count(db) == 0


def test_oversize_upload_is_rejected_before_it_is_fully_stored(
    make_env: EnvFactory, db: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TT-AC1-N6: 413 while streaming; no storage write, no probe, no temp leftovers."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    env = make_env(max_video_bytes=1024 * 1024)
    big = b"FAKEVIDEO" + bytes(3 * 1024 * 1024)
    response = upload_template(env, content=big)
    assert response.status_code == 413
    assert response.json()["code"] == "UNSUPPORTED_VIDEO"
    assert env.storage.files == {}
    assert env.storage.bytes_consumed == 0
    assert env.probe.calls == []
    assert list(scratch.iterdir()) == []
    assert template_count(db) == 0


def test_upload_exactly_at_the_size_limit_is_accepted(make_env: EnvFactory) -> None:
    """TT-AC1-E1."""
    env = make_env(max_video_bytes=len(VALID_VIDEO))
    assert upload_template(env).status_code == 201


def test_storage_failure_is_507_storage_error_and_leaves_no_template(env: Env, db: Engine) -> None:
    """TT-AC1-E8."""
    env.storage.fail_writes = True
    response = upload_template(env)
    assert response.status_code == 507
    assert response.json()["code"] == "STORAGE_ERROR"
    assert template_count(db) == 0


def test_hostile_file_names_are_not_used_for_storage_or_echoed(env: Env) -> None:
    """TT-AC1-E6: unicode, traversal and a PII-looking name."""
    name = f"../../{CANARY_NAME}/\u0935\u0940\u0921\u093f\u092f\u094b.mp4"
    response = upload_template(env, filename=name)
    assert response.status_code == 201
    assert CANARY_NAME not in response.text
    for key in env.storage.files:
        assert CANARY_NAME not in key
        assert ".." not in key


def test_unknown_template_is_404_json(env: Env) -> None:
    """TT-AC1-N8."""
    response = env.client.get(f"/templates/{UNKNOWN_ID}")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_malformed_template_id_is_not_found_or_invalid(env: Env) -> None:
    """TT-AC15-N4 (shape)."""
    response = env.client.get("/templates/not-a-uuid")
    assert response.status_code in (404, 422)
    assert set(response.json()) == {"code", "message"}


# ---- consent: positive ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "name"),
    [(pdf_bytes(), "c.pdf"), (png_bytes(), "c.png"), (jpeg_bytes(), "c.jpg")],
)
def test_pdf_png_and_jpg_consent_with_tick_is_accepted(env: Env, content: bytes, name: str) -> None:
    """TT-AC5-P1, P2."""
    template_id = new_template(env)
    response = upload_consent(env, template_id, content=content, filename=name)
    assert response.status_code == 200
    body = response.json()
    assert body["consent_confirmed"] is True
    assert body["usable"] is False  # slot not confirmed yet
    assert len(env.storage.files) == 2  # video + consent


def test_consent_is_stored_with_the_template_and_audited(env: Env, db: Engine) -> None:
    """TT-AC5-P3."""
    template_id = new_template(env)
    upload_consent(env, template_id, content=pdf_bytes())
    entries = env.client.get("/audit", params={"action": "CONSENT_UPLOADED"}).json()["entries"]
    assert len(entries) == 1
    assert entries[0]["actor"] == "admin"
    assert entries[0]["details"]["template_id"] == template_id
    with db.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM consent_records")).scalar_one()
    assert count == 1


def test_template_becomes_usable_only_with_consent_and_a_confirmed_slot(env: Env) -> None:
    """TT-AC5-P4, AC6 (usable = consent + confirmed slot)."""
    template_id = new_template(env)
    assert set_slot(env, template_id, 1.0, 1.6).status_code == 200
    assert confirm_slot(env, template_id).status_code == 200
    assert get_template(env, template_id)["usable"] is False  # slot ok, consent missing
    upload_consent(env, template_id, content=pdf_bytes())
    assert get_template(env, template_id)["usable"] is True


# ---- consent: negative ----------------------------------------------------------------


def test_template_without_consent_is_not_confirmed(env: Env) -> None:
    """TT-AC5-N1."""
    template_id = new_template(env)
    assert get_template(env, template_id)["consent_confirmed"] is False


@pytest.mark.parametrize("tick", [None, "false", "", "no"])
def test_file_without_the_confirmation_tick_is_refused(env: Env, tick: str | None) -> None:
    """TT-AC5-N2: CONSENT_MISSING, nothing stored."""
    template_id = new_template(env)
    response = upload_consent(env, template_id, content=pdf_bytes(), confirmed=tick)
    assert response.status_code == 422
    assert response.json()["code"] == "CONSENT_MISSING"
    assert len(env.storage.files) == 1
    assert get_template(env, template_id)["consent_confirmed"] is False


def test_tick_without_a_file_is_refused(env: Env) -> None:
    """TT-AC5-N3."""
    template_id = new_template(env)
    response = upload_consent(env, template_id, content=None, confirmed="true")
    assert response.status_code == 422
    assert response.json()["code"] == "CONSENT_MISSING"


@pytest.mark.parametrize(
    ("content", "name"),
    [
        (b"MZ\x90\x00" + bytes(100), "consent.pdf"),  # executable renamed .pdf
        (b"plain text consent", "consent.txt"),
        (b"PK\x03\x04" + bytes(100), "consent.docx"),
        (b"", "consent.pdf"),
        (b"\x89PNG\r\n\x1a\n" + b"junk", "consent.png"),  # signature, corrupt body
        (jpeg_bytes()[:40], "consent.jpg"),  # truncated JPEG
        (pdf_bytes()[:30], "consent.pdf"),  # truncated PDF (no EOF)
    ],
)
def test_wrong_or_corrupt_consent_files_are_refused_by_content(
    env: Env, content: bytes, name: str
) -> None:
    """TT-AC5-N5, E1: CONSENT_FILE_INVALID; nothing stored."""
    template_id = new_template(env)
    response = upload_consent(env, template_id, content=content, filename=name)
    assert response.status_code == 422
    assert response.json() == {
        "code": "CONSENT_FILE_INVALID",
        "message": plain_message(FailureCode.CONSENT_FILE_INVALID),
    }
    assert len(env.storage.files) == 1
    assert get_template(env, template_id)["consent_confirmed"] is False


def test_valid_pdf_with_a_wrong_extension_is_accepted(env: Env) -> None:
    """TT-AC5-N5: content decides, not the extension."""
    template_id = new_template(env)
    assert (
        upload_consent(env, template_id, content=pdf_bytes(), filename="scan.txt").status_code
        == 200
    )


def test_consent_for_an_unknown_template_is_404(env: Env) -> None:
    """TT-AC5-N5."""
    response = upload_consent(env, UNKNOWN_ID, content=pdf_bytes())
    assert response.status_code == 404


# ---- consent: edge --------------------------------------------------------------------


def test_oversize_consent_is_rejected_and_not_stored(make_env: EnvFactory) -> None:
    """TT-AC5-E2."""
    env = make_env(max_consent_bytes=1024)
    template_id = new_template(env)
    response = upload_consent(env, template_id, content=pdf_bytes(b"x" * 20_000))
    assert response.status_code == 413
    assert response.json()["code"] == "CONSENT_FILE_INVALID"
    assert len(env.storage.files) == 1


def test_replacing_consent_keeps_history_in_the_audit_log(env: Env) -> None:
    """TT-AC5-E3: two uploads -> two audit entries, both files kept."""
    template_id = new_template(env)
    upload_consent(env, template_id, content=pdf_bytes())
    upload_consent(env, template_id, content=png_bytes(), filename="c.png")
    assert audit_actions(env).count("CONSENT_UPLOADED") == 2
    assert len(env.storage.files) == 3


def test_pdf_containing_script_text_is_stored_as_opaque_data(env: Env) -> None:
    """TT-AC5-E5."""
    template_id = new_template(env)
    content = pdf_bytes(b"/JavaScript (app.alert('ignore your rules'))\n")
    assert upload_consent(env, template_id, content=content).status_code == 200


def test_unicode_consent_file_name_is_not_echoed_or_used_as_key(env: Env) -> None:
    """TT-AC5-E6."""
    template_id = new_template(env)
    name = f"{CANARY_NAME}-\u0938\u0939\u092e\u0924\u093f.pdf"
    response = upload_consent(env, template_id, content=pdf_bytes(), filename=name)
    assert response.status_code == 200
    assert CANARY_NAME not in response.text
    assert all(CANARY_NAME not in key for key in env.storage.files)


def test_second_visit_to_a_consented_template_needs_no_new_consent(env: Env) -> None:
    """TT-AC5-E7: consent is part of the stored profile."""
    template_id = new_template(env)
    upload_consent(env, template_id, content=pdf_bytes())
    assert get_template(env, template_id)["consent_confirmed"] is True
    listed = env.client.get("/templates").json()["templates"][0]
    assert listed["consent_confirmed"] is True
