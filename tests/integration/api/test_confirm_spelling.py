"""L6a: POST /batches/{id}/preview/confirm-spelling and the local-mode approval gate (AC5).

Local mode needs a transliterator; the real one would load weights, so a stub is swapped in
where the container builds its adapters.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tests.integration.api.batch_helpers import (
    new_batch,
    post_action,
    start,
)
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.helpers import audit_actions
from tests.integration.api.test_batches_start import UNKNOWN_ID, render_preview
from vidgen.infrastructure.db.models import Batch
from vidgen.infrastructure.local_ai import factory as ai_factory

HINDI = "कृष्ण कुमार"
SUGGESTION = "सुझाव"
CANARY = "Zqéran-Canary"


class StubTransliterator:
    """Returns a fixed guess; never touches weights."""

    def transliterate(self, text: str, target_script: str) -> str:
        """Return the canned suggestion."""
        return SUGGESTION


def confirm(env: Env, batch_id: str, name: Any) -> Any:
    """POST confirm-spelling with a JSON body."""
    return env.client.post(
        f"/batches/{batch_id}/preview/confirm-spelling",
        json={"spoken_name": name},
        headers=env.csrf,
    )


@pytest.fixture
def local(make_env: EnvFactory, monkeypatch: pytest.MonkeyPatch) -> Env:
    """A logged-in environment in local AI mode with a stub transliterator."""
    real: Callable[..., Any] = ai_factory.build_ai_adapters

    def patched(settings: Any) -> Any:
        return dataclasses.replace(real(settings), transliterator=StubTransliterator())

    monkeypatch.setattr("vidgen.api.container.build_ai_adapters", patched)
    return make_env(ai_mode="local")


def ready_preview(env: Env) -> str:
    """A DRAFT batch whose preview the 'worker' has finished."""
    batch_id = new_batch(env)
    assert post_action(env, batch_id, "preview").status_code == 202
    render_preview(env, batch_id)
    return batch_id


def preview_of(env: Env, batch_id: str) -> dict[str, Any]:
    """The preview object of GET /batches/{id}."""
    body: dict[str, Any] = env.client.get(f"/batches/{batch_id}").json()["preview"]
    return body


# ---- positive -------------------------------------------------------------------------


def test_confirm_stores_the_name_and_marks_it_confirmed(local: Env) -> None:
    batch_id = ready_preview(local)
    response = confirm(local, batch_id, HINDI)
    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["spoken_name"] == HINDI
    assert preview["spoken_name_confirmed"] is True
    assert preview_of(local, batch_id)["spoken_name"] == HINDI


def test_ready_preview_offers_the_suggestion_before_confirmation(local: Env) -> None:
    batch_id = ready_preview(local)
    preview = preview_of(local, batch_id)
    assert preview["suggested_spoken_name"] == SUGGESTION
    assert preview["spoken_name"] is None
    assert preview["spoken_name_confirmed"] is False


def test_the_name_is_trimmed(local: Env) -> None:
    batch_id = ready_preview(local)
    assert confirm(local, batch_id, f"  {HINDI}  ").json()["preview"]["spoken_name"] == HINDI


def test_after_confirmation_approve_succeeds(local: Env) -> None:
    batch_id = ready_preview(local)
    assert confirm(local, batch_id, HINDI).status_code == 200
    assert post_action(local, batch_id, "preview/approve").status_code == 200
    assert preview_of(local, batch_id)["approved"] is True


def test_confirming_is_recorded_in_the_audit_log(local: Env) -> None:
    batch_id = ready_preview(local)
    confirm(local, batch_id, HINDI)
    assert "SPOKEN_NAME_CONFIRMED" in audit_actions(local)


@pytest.mark.parametrize("name", ["A", "ए", "x" * 200, "Zoë O'Brien-Smith"])
def test_boundary_and_special_names_are_accepted(local: Env, name: str) -> None:
    batch_id = ready_preview(local)
    assert confirm(local, batch_id, name).json()["preview"]["spoken_name"] == name


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_empty_or_too_long_name_is_422(local: Env, name: str) -> None:
    batch_id = ready_preview(local)
    assert confirm(local, batch_id, name).status_code == 422
    assert preview_of(local, batch_id)["spoken_name_confirmed"] is False


@pytest.mark.parametrize("body", [{}, {"spoken_name": None}, {"spoken_name": 5}])
def test_missing_or_wrong_type_is_422(local: Env, body: dict[str, Any]) -> None:
    batch_id = ready_preview(local)
    response = local.client.post(
        f"/batches/{batch_id}/preview/confirm-spelling", json=body, headers=local.csrf
    )
    assert response.status_code == 422


def test_confirm_before_the_preview_is_ready_is_409_preview_not_ready(local: Env) -> None:
    batch_id = new_batch(local)
    response = confirm(local, batch_id, HINDI)
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_READY"


def test_confirm_while_the_preview_is_pending_is_409(local: Env) -> None:
    batch_id = new_batch(local)
    post_action(local, batch_id, "preview")
    assert confirm(local, batch_id, HINDI).json()["code"] == "PREVIEW_NOT_READY"


def test_confirm_on_a_started_batch_is_409_invalid_state(local: Env) -> None:
    batch_id = ready_preview(local)
    assert confirm(local, batch_id, HINDI).status_code == 200
    assert post_action(local, batch_id, "preview/approve").status_code == 200
    assert start(local, batch_id).status_code == 200
    response = confirm(local, batch_id, HINDI)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


def test_confirm_on_an_unknown_batch_is_404(local: Env) -> None:
    assert confirm(local, UNKNOWN_ID, HINDI).status_code == 404


def test_confirm_needs_a_session_and_csrf(make_env: EnvFactory) -> None:
    anon = make_env(login=False)
    response = anon.client.post(
        f"/batches/{UNKNOWN_ID}/preview/confirm-spelling", json={"spoken_name": "x"}
    )
    assert response.status_code == 401


def test_approve_before_confirmation_in_local_mode_is_409(local: Env) -> None:
    batch_id = ready_preview(local)
    response = post_action(local, batch_id, "preview/approve")
    assert response.status_code == 409
    assert response.json()["code"] == "SPELLING_NOT_CONFIRMED"
    assert preview_of(local, batch_id)["approved"] is False


# ---- edge -----------------------------------------------------------------------------


def test_confirming_again_withdraws_an_earlier_approval(local: Env) -> None:
    batch_id = ready_preview(local)
    confirm(local, batch_id, HINDI)
    post_action(local, batch_id, "preview/approve")
    assert confirm(local, batch_id, "नया नाम").status_code == 200
    preview = preview_of(local, batch_id)
    assert preview["approved"] is False
    assert preview["spoken_name"] == "नया नाम"


def test_a_new_preview_resets_the_confirmation(local: Env) -> None:
    batch_id = ready_preview(local)
    confirm(local, batch_id, HINDI)
    assert post_action(local, batch_id, "preview").status_code == 202
    preview = preview_of(local, batch_id)
    assert preview["spoken_name_confirmed"] is False
    assert preview["spoken_name"] is None
    render_preview(local, batch_id)
    assert post_action(local, batch_id, "preview/approve").status_code == 409


def test_spoken_name_never_reaches_logs_or_audit(
    local: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    batch_id = ready_preview(local)
    confirm(local, batch_id, CANARY)
    assert CANARY not in caplog.text
    audit = json.dumps(local.client.get("/audit").json(), ensure_ascii=False)
    assert CANARY not in audit


def test_spoken_name_is_stored_encrypted_in_the_column_mapping(local: Env, db: Engine) -> None:
    batch_id = ready_preview(local)
    confirm(local, batch_id, CANARY)
    with Session(db) as session:
        document = session.execute(select(Batch.column_mapping)).scalars().all()[-1]
    text = json.dumps(document, ensure_ascii=False)
    assert CANARY not in text
    assert document["preview"]["spoken_name_enc"]


def test_encrypted_name_survives_a_new_app_instance(local: Env) -> None:
    """Stateless API: the confirmation is read back from the database, not from memory."""
    batch_id = ready_preview(local)
    confirm(local, batch_id, HINDI)
    peer = local.new_instance()
    assert peer.login().status_code == 200
    assert preview_of(peer, batch_id)["spoken_name"] == HINDI


# ---- fake mode ------------------------------------------------------------------------


def test_fake_mode_preview_shape_is_unchanged(env: Env) -> None:
    batch_id = new_batch(env)
    post_action(env, batch_id, "preview")
    render_preview(env, batch_id)
    assert preview_of(env, batch_id) == {"status": "READY", "approved": False, "stage": None}


def test_fake_mode_approve_needs_no_confirmation(env: Env) -> None:
    batch_id = new_batch(env)
    post_action(env, batch_id, "preview")
    render_preview(env, batch_id)
    assert post_action(env, batch_id, "preview/approve").status_code == 200
