"""DD-38: a regenerated preview keeps the spoken name the human confirmed (local AI mode).

Regenerating the preview starts a new preview record. The confirmed spelling must survive that
record, so the next render speaks the confirmed text. Everything else about the regenerate
request stays as it was: PENDING status, the fingerprint, approval cleared, old file deleted.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from tests.integration.api.batch_helpers import (
    new_batch,
    post_action,
    start,
)
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.test_batches_start import render_preview
from vidgen.infrastructure.local_ai import factory as ai_factory

HINDI = "कृष्ण कुमार"
NEW_HINDI = "नया नाम"
SUGGESTION = "सुझाव"
SHAPES = ["ए", "x" * 200, "Zoë O'Brien-Smith"]


class StubTransliterator:
    """Returns a fixed guess; never touches weights."""

    def transliterate(self, text: str, target_script: str) -> str:
        """Return the canned suggestion."""
        return SUGGESTION


@pytest.fixture
def local(make_env: EnvFactory, monkeypatch: pytest.MonkeyPatch) -> Env:
    """A logged-in environment in local AI mode with a stub transliterator."""
    real: Callable[..., Any] = ai_factory.build_ai_adapters

    def patched(settings: Any) -> Any:
        return dataclasses.replace(real(settings), transliterator=StubTransliterator())

    monkeypatch.setattr("vidgen.api.container.build_ai_adapters", patched)
    return make_env(ai_mode="local")


def confirm(env: Env, batch_id: str, name: str) -> Any:
    """POST confirm-spelling with a JSON body."""
    return env.client.post(
        f"/batches/{batch_id}/preview/confirm-spelling",
        json={"spoken_name": name},
        headers=env.csrf,
    )


def regenerate(env: Env, batch_id: str) -> None:
    """POST /batches/{id}/preview again; must be accepted."""
    response = post_action(env, batch_id, "preview")
    assert response.status_code == 202, response.text


def ready_preview(env: Env) -> str:
    """A DRAFT batch whose preview the 'worker' has finished."""
    batch_id = new_batch(env)
    regenerate(env, batch_id)
    render_preview(env, batch_id)
    return batch_id


def preview_of(env: Env, batch_id: str) -> dict[str, Any]:
    """The preview object of GET /batches/{id}."""
    body: dict[str, Any] = env.client.get(f"/batches/{batch_id}").json()["preview"]
    return body


def confirmed_then_regenerated(env: Env, name: str = HINDI) -> str:
    """Ready preview, confirmed name, then a regenerate request (the CEO's bug path)."""
    batch_id = ready_preview(env)
    assert confirm(env, batch_id, name).status_code == 200
    regenerate(env, batch_id)
    return batch_id


# ---- positive -------------------------------------------------------------------------


def test_regenerate_keeps_the_confirmed_name_in_the_preview_json(local: Env) -> None:
    """DD-38 K-P1: confirm, then regenerate: the name and its confirmed flag survive."""
    batch_id = confirmed_then_regenerated(local)
    preview = preview_of(local, batch_id)
    assert preview["status"] == "PENDING"
    assert preview["spoken_name"] == HINDI
    assert preview["spoken_name_confirmed"] is True


def test_regenerate_twice_keeps_the_confirmed_name(local: Env) -> None:
    """DD-38 K-P2: a render in between does not drop the name either."""
    batch_id = confirmed_then_regenerated(local)
    render_preview(local, batch_id)
    regenerate(local, batch_id)
    preview = preview_of(local, batch_id)
    assert preview["spoken_name"] == HINDI
    assert preview["spoken_name_confirmed"] is True


def test_approve_after_regenerate_succeeds_with_the_kept_name(local: Env) -> None:
    """DD-38 K-P3: the operator can approve the new render without confirming again."""
    batch_id = confirmed_then_regenerated(local)
    render_preview(local, batch_id)
    assert post_action(local, batch_id, "preview/approve").status_code == 200
    assert preview_of(local, batch_id)["approved"] is True


@pytest.mark.parametrize("name", SHAPES)
def test_regenerate_keeps_every_accepted_name_shape(local: Env, name: str) -> None:
    """DD-38 K-P4: Devanagari, the 200-character maximum, Latin with apostrophe and hyphen."""
    batch_id = confirmed_then_regenerated(local, name)
    assert preview_of(local, batch_id)["spoken_name"] == name


def test_kept_name_survives_a_new_app_instance(local: Env) -> None:
    """DD-38 K-P5: stateless API: the kept name is read back from the database."""
    batch_id = confirmed_then_regenerated(local)
    peer = local.new_instance()
    assert peer.login().status_code == 200
    preview = preview_of(peer, batch_id)
    assert preview["spoken_name"] == HINDI
    assert preview["spoken_name_confirmed"] is True


# ---- negative -------------------------------------------------------------------------


def test_regenerate_after_start_is_409_and_keeps_the_name(local: Env) -> None:
    """DD-38 K-N1: a started batch cannot be re-previewed; its confirmed name is untouched."""
    batch_id = ready_preview(local)
    assert confirm(local, batch_id, HINDI).status_code == 200
    approve_preview_flow(local, batch_id)
    assert start(local, batch_id).status_code == 200
    response = post_action(local, batch_id, "preview")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"
    assert preview_of(local, batch_id)["spoken_name"] == HINDI


def test_regenerate_without_confirmation_keeps_spoken_name_null(local: Env) -> None:
    """DD-38 K-N2: nothing was confirmed, so there is nothing to keep: spoken_name stays null."""
    batch_id = ready_preview(local)
    regenerate(local, batch_id)
    preview = preview_of(local, batch_id)
    assert preview["spoken_name"] is None
    assert preview["spoken_name_confirmed"] is False


# ---- edge -----------------------------------------------------------------------------


def test_regenerate_clears_approval_and_keeps_the_name(local: Env) -> None:
    """DD-38 K-E1: the approval is still withdrawn, but the spelling is not."""
    batch_id = ready_preview(local)
    confirm(local, batch_id, HINDI)
    approve_preview_flow(local, batch_id)
    regenerate(local, batch_id)
    preview = preview_of(local, batch_id)
    assert preview["approved"] is False
    assert preview["spoken_name"] == HINDI


def test_confirming_again_then_regenerate_keeps_the_new_name(local: Env) -> None:
    """DD-38 K-E2: the newest confirmation overrides the kept one."""
    batch_id = confirmed_then_regenerated(local)
    render_preview(local, batch_id)
    assert confirm(local, batch_id, NEW_HINDI).status_code == 200
    regenerate(local, batch_id)
    assert preview_of(local, batch_id)["spoken_name"] == NEW_HINDI


def test_regenerate_still_resets_status_and_deletes_the_old_file(local: Env) -> None:
    """DD-38 K-E3: only the spoken name changes its behaviour; the rest is as before."""
    batch_id = ready_preview(local)
    old_key = f"previews/{batch_id}.mp4"
    assert old_key in local.storage.files
    regenerate(local, batch_id)
    assert preview_of(local, batch_id)["status"] == "PENDING"
    assert old_key not in local.storage.files


def test_no_confirmation_stays_null_across_regenerations(local: Env) -> None:
    """DD-38 K-E4: regenerating several times without a confirmation never invents a name."""
    batch_id = ready_preview(local)
    for _ in range(2):
        regenerate(local, batch_id)
        render_preview(local, batch_id)
    assert preview_of(local, batch_id)["spoken_name"] is None


def approve_preview_flow(env: Env, batch_id: str) -> None:
    """Render the current preview and approve it (the spelling must already be confirmed)."""
    render_preview(env, batch_id)
    assert post_action(env, batch_id, "preview/approve").status_code == 200
