"""RP-API: the chooser at preview approval (AC3, AC4, AC5, AC8). Contract: docs/test-
  tree/render-providers.md.

Registry: ``local-mac`` (real data, no cap) and ``modal-demo`` (demo only, cap 5.0 USD, 0.001 USD/s,
needs MODAL_TOKEN_ID and MODAL_TOKEN_SECRET). Fake heartbeats; no worker and no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from tests.fixtures.providers import REGISTRY_TOML
from tests.integration.api.batch_helpers import (
    get_batch,
    new_batch,
    people,
    post_action,
    row_status,
    set_batch,
)
from tests.integration.api.conftest import Env
from tests.integration.api.provider_helpers import (
    LOCAL_QUEUE,
    MODAL_QUEUE,
    add_measured_runs,
    approve_with,
    build_env,
    demo_batch,
    listed,
    providers_of,
    render_preview,
    start_batch,
)

NOT_MEASURED = "not measured yet"


@pytest.fixture
def env(db: Engine, test_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return build_env(db, test_db_url, tmp_path, monkeypatch)


def approved(env: Env, batch_id: str, provider_id: str | None):  # type: ignore[no-untyped-def]
    render_preview(env, batch_id)
    return approve_with(env, batch_id, provider_id)


# ---- positive -------------------------------------------------------------------------


def test_the_list_has_the_pinned_shape_for_every_registered_provider(env: Env) -> None:
    """RP-API-P1."""
    batch_id = demo_batch(env)
    body = providers_of(env, batch_id)
    assert body["data_class"] == "demo"
    assert body["selected_provider_id"] is None
    assert body["any_selectable"] is True
    assert [p["id"] for p in body["providers"]] == ["local-mac", "modal-demo"]
    modal = listed(env, batch_id, "modal-demo")
    assert set(modal) == {
        "id",
        "name",
        "kind",
        "data_rule",
        "setup",
        "estimate",
        "estimate_label",
        "spend_cap_usd",
        "spent_usd",
        "remaining_usd",
        "selectable",
        "refusal",
    }
    assert modal["kind"] == "remote_function"
    assert modal["data_rule"] == "demo_only"
    assert modal["setup"] == {"state": "ready", "reason": None}
    assert (modal["spend_cap_usd"], modal["spent_usd"], modal["remaining_usd"]) == (5.0, 0, 5.0)
    assert modal["selectable"] is True
    assert modal["refusal"] is None


def test_a_demo_batch_can_choose_the_remote_provider_and_it_is_stored(env: Env) -> None:
    """RP-API-P2."""
    batch_id = demo_batch(env)
    response = approved(env, batch_id, "modal-demo")
    assert response.status_code == 200, response.text
    assert response.json()["provider_id"] == "modal-demo"
    assert get_batch(env, batch_id)["provider_id"] == "modal-demo"
    assert providers_of(env, batch_id)["selected_provider_id"] == "modal-demo"


def test_estimates_come_from_three_measured_rows_of_that_provider(env: Env, db: Engine) -> None:
    """RP-API-P3 (AC3): median 100 s, cost 0.1 USD per video, batch of 3 rows."""
    add_measured_runs(env, db, "modal-demo", seconds=100.0, cost=0.1, count=3)
    batch_id = demo_batch(env, 3)
    modal = listed(env, batch_id, "modal-demo")
    assert modal["estimate"]["seconds_per_video"] == pytest.approx(100.0)
    assert modal["estimate"]["batch_seconds"] == pytest.approx(300.0)
    assert modal["estimate"]["batch_cost_usd"] == pytest.approx(0.3)  # 300 s x 0.001
    assert modal["estimate_label"] is None
    assert modal["spent_usd"] == pytest.approx(0.3)
    assert modal["remaining_usd"] == pytest.approx(4.7)


def test_an_old_client_that_approves_without_a_body_keeps_the_default_provider(env: Env) -> None:
    """RP-API-P4 (R5): no body = no choice; the batch starts exactly as before."""
    batch_id = new_batch(env, people(2))
    render_preview(env, batch_id)
    assert approve_with(env, batch_id, None).status_code == 200
    assert get_batch(env, batch_id)["provider_id"] is None
    assert start_batch(env, batch_id).status_code == 200


# ---- negative -------------------------------------------------------------------------


def test_not_measured_yet_is_shown_with_fewer_than_three_runs(env: Env, db: Engine) -> None:
    """RP-API-N1: 2 runs of this provider are not enough, and failed rows never count."""
    add_measured_runs(env, db, "modal-demo", count=2)
    add_measured_runs(env, db, "modal-demo", count=3, status="FAILED")
    batch_id = demo_batch(env)
    modal = listed(env, batch_id, "modal-demo")
    assert modal["estimate"] is None
    assert modal["estimate_label"] == NOT_MEASURED


def test_rows_rendered_by_another_provider_are_never_counted(env: Env, db: Engine) -> None:
    """RP-API-N2."""
    add_measured_runs(env, db, "local-mac", seconds=7.0, cost=0.0, count=3)
    batch_id = demo_batch(env)
    assert listed(env, batch_id, "modal-demo")["estimate"] is None
    local = listed(env, batch_id, "local-mac")
    assert local["estimate"]["seconds_per_video"] == pytest.approx(7.0)
    assert local["estimate"]["batch_cost_usd"] == 0
    assert local["remaining_usd"] is None
    assert local["spend_cap_usd"] is None


def test_a_demo_only_provider_is_listed_but_refused_for_a_real_batch(env: Env) -> None:
    """RP-API-N3 (AC8): the list says why, and approve answers 409 PROVIDER_NOT_ALLOWED."""
    batch_id = new_batch(env, people(2))
    modal = listed(env, batch_id, "modal-demo")
    assert modal["selectable"] is False
    assert modal["refusal"]["code"] == "data_class"
    assert modal["refusal"]["reason"]
    response = approved(env, batch_id, "modal-demo")
    assert response.status_code == 409
    assert response.json()["code"] == "PROVIDER_NOT_ALLOWED"
    assert get_batch(env, batch_id)["provider_id"] is None
    assert get_batch(env, batch_id)["preview"]["approved"] is False


def test_an_estimate_above_the_remaining_credit_is_refused_by_the_api_too(
    env: Env, db: Engine
) -> None:
    """RP-API-N4 (AC5): spent 4.8 of 5.0; the batch would cost 0.3."""
    add_measured_runs(env, db, "modal-demo", seconds=100.0, cost=1.6, count=3)
    batch_id = demo_batch(env, 3)
    modal = listed(env, batch_id, "modal-demo")
    assert modal["selectable"] is False
    assert modal["refusal"]["code"] == "over_credit"
    response = approved(env, batch_id, "modal-demo")
    assert response.status_code == 409
    assert response.json()["code"] == "PROVIDER_OVER_CREDIT"
    assert get_batch(env, batch_id)["provider_id"] is None


def test_a_provider_that_is_not_ready_is_greyed_with_its_reason_and_refused(
    db: Engine, test_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RP-API-N5 (AC4): missing env var and no worker."""
    env = build_env(db, test_db_url, tmp_path, monkeypatch, alive={LOCAL_QUEUE}, modal_env=False)
    batch_id = demo_batch(env)
    modal = listed(env, batch_id, "modal-demo")
    assert modal["setup"]["state"] == "needs_setup"
    assert "MODAL_TOKEN_ID" in modal["setup"]["reason"]
    assert modal["selectable"] is False
    assert modal["refusal"]["code"] == "not_ready"
    response = approved(env, batch_id, "modal-demo")
    assert (response.status_code, response.json()["code"]) == (409, "PROVIDER_NOT_READY")


def test_a_missing_worker_alone_makes_a_provider_needs_setup(
    db: Engine, test_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RP-API-N6."""
    env = build_env(db, test_db_url, tmp_path, monkeypatch, alive={LOCAL_QUEUE})
    modal = listed(env, demo_batch(env), "modal-demo")
    assert modal["setup"] == {"state": "needs_setup", "reason": "worker not running"}


def test_an_unknown_provider_id_is_a_422_and_changes_nothing(env: Env) -> None:
    """RP-API-N7."""
    batch_id = demo_batch(env)
    response = approved(env, batch_id, "ghost")
    assert (response.status_code, response.json()["code"]) == (422, "UNKNOWN_PROVIDER")
    assert get_batch(env, batch_id)["provider_id"] is None


def test_the_provider_list_of_an_unknown_batch_is_404(env: Env) -> None:
    """RP-API-N8."""
    response = env.client.get("/batches/00000000-0000-4000-8000-000000000000/providers")
    assert response.status_code == 404


# ---- edge -----------------------------------------------------------------------------


def test_when_no_provider_is_selectable_the_list_says_so(
    db: Engine, test_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RP-API-E1: no worker anywhere -> clear message; the batch cannot be started with a choice."""
    env = build_env(db, test_db_url, tmp_path, monkeypatch, alive=set())
    batch_id = demo_batch(env)
    body = providers_of(env, batch_id)
    assert body["any_selectable"] is False
    assert body["message"]
    assert not any(p["selectable"] for p in body["providers"])
    assert approved(env, batch_id, "local-mac").status_code == 409


def test_a_provider_that_stops_being_ready_before_start_blocks_the_start(
    env: Env, db: Engine
) -> None:
    """RP-API-E2: nothing queued, the batch stays a draft."""
    batch_id = demo_batch(env)
    assert approved(env, batch_id, "modal-demo").status_code == 200
    env.heartbeats.alive.discard(MODAL_QUEUE)  # type: ignore[attr-defined]
    response = start_batch(env, batch_id)
    assert (response.status_code, response.json()["code"]) == (409, "PROVIDER_NOT_READY")
    assert get_batch(env, batch_id)["status"] == "DRAFT"
    assert env.queue.rows == []
    assert set(row_status(db, batch_id).values()) <= {"QUEUED"}


def test_picking_an_unmeasured_capped_provider_is_allowed_and_labelled(env: Env) -> None:
    """RP-API-E3 (Q2 = yes)."""
    batch_id = demo_batch(env)
    modal = listed(env, batch_id, "modal-demo")
    assert modal["estimate"] is None
    assert modal["estimate_label"] == NOT_MEASURED
    assert modal["selectable"] is True
    assert approved(env, batch_id, "modal-demo").status_code == 200


def test_choosing_again_before_start_replaces_the_choice(env: Env) -> None:
    """RP-API-E4."""
    batch_id = demo_batch(env)
    assert approved(env, batch_id, "modal-demo").status_code == 200
    assert approve_with(env, batch_id, "local-mac").status_code == 200
    assert get_batch(env, batch_id)["provider_id"] == "local-mac"


def test_the_batch_json_exposes_provider_data_class_spend_and_pause_reason(
    env: Env, db: Engine
) -> None:
    """RP-API-E5 (pause reason shown by the dashboard)."""
    batch_id = demo_batch(env)
    body = get_batch(env, batch_id)
    assert (body["provider_id"], body["data_class"], body["spent_usd"]) == (None, "demo", 0)
    assert body["pause_reason"] is None
    set_batch(db, batch_id, provider_id="modal-demo", status="PAUSED")
    assert post_action(env, batch_id, "pause").status_code == 200  # idempotent
    assert get_batch(env, batch_id)["pause_reason"] is None  # paused by hand, nothing near the cap


def test_registry_file_is_the_source_of_the_provider_list(env: Env) -> None:
    """RP-API-E6: the fixture TOML has exactly these two entries."""
    assert REGISTRY_TOML.count("[[provider]]") == len(
        providers_of(env, demo_batch(env))["providers"]
    )
