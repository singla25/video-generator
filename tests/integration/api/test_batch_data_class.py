"""RP-API: the data class of a batch is declared at upload (C5, AC8).

``POST /batches`` takes ``data_class`` ("real" default | "demo") and, for demo,
  ``confirm_demo=true``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from tests.integration.api.batch_helpers import get_batch, row_ids, set_batch, set_rows
from tests.integration.api.conftest import Env
from tests.integration.api.provider_helpers import (
    add_measured_runs,
    build_env,
    create_with_class,
    demo_batch,
)


@pytest.fixture
def env(db: Engine, test_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return build_env(db, test_db_url, tmp_path, monkeypatch, row_timeout_seconds=100)


def test_a_batch_without_the_field_is_real_data_with_no_provider(env: Env) -> None:
    """RP-DC-P1: the default is the safe one."""
    response = create_with_class(env)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["data_class"], body["provider_id"], body["spent_usd"]) == ("real", None, 0)
    assert body["pause_reason"] is None


def test_a_demo_batch_with_confirmation_is_created_as_demo(env: Env) -> None:
    """RP-DC-P2."""
    batch_id = demo_batch(env)
    assert get_batch(env, batch_id)["data_class"] == "demo"


@pytest.mark.parametrize("confirm", [None, "", "false", "no"])
def test_demo_without_an_explicit_confirmation_is_refused(env: Env, confirm: str | None) -> None:
    """RP-DC-N1: no batch is created."""
    response = create_with_class(env, data_class="demo", confirm_demo=confirm)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert env.client.get("/batches").json()["total"] == 0


@pytest.mark.parametrize("value", ["Real", "test", "", "demo,real"])
def test_an_unknown_data_class_is_refused(env: Env, value: str) -> None:
    """RP-DC-N2."""
    assert create_with_class(env, data_class=value, confirm_demo="true").status_code == 422


def test_confirmation_alone_does_not_turn_a_real_batch_into_demo(env: Env) -> None:
    """RP-DC-E1."""
    response = create_with_class(env, data_class="real", confirm_demo="true")
    assert response.status_code == 201
    assert response.json()["data_class"] == "real"


def test_batch_spent_usd_is_the_sum_of_its_rows_and_the_pause_reason_names_the_cap(
    env: Env, db: Engine
) -> None:
    """RP-DC-E2 (AC7): cap 5.0, spent 4.95, worst case of one row 100 s x 0.001 = 0.1 -> would
    pass."""
    batch_id = add_measured_runs(env, db, "modal-demo", seconds=10.0, cost=1.65, count=3)
    set_batch(db, batch_id, status="PAUSED", data_class="demo")
    body = get_batch(env, batch_id)
    assert body["spent_usd"] == pytest.approx(4.95)
    assert body["pause_reason"] == "spend cap reached"
    set_batch(db, batch_id, status="RUNNING")
    assert get_batch(env, batch_id)["pause_reason"] is None


def test_a_paused_real_batch_on_a_demo_only_provider_says_why(env: Env, db: Engine) -> None:
    """RP-DC-E3: what the worker leaves behind when it refuses (see worker tests)."""
    batch_id = add_measured_runs(env, db, "modal-demo", count=3)
    set_batch(db, batch_id, status="PAUSED")
    set_rows(db, batch_id, list(row_ids(db, batch_id)), status="QUEUED", cost_usd=None)
    assert get_batch(env, batch_id)["pause_reason"] == "provider not allowed for this data class"
