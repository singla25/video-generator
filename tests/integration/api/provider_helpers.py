"""Helpers for the render-provider API tests: an app with a provider registry and fake heartbeats.

The app is built like ``make_env`` but with ``Settings.providers_file`` and
  ``AppDeps.queue_heartbeats``
(per-queue worker heartbeats). Environment variables for ``requires_env`` come from ``monkeypatch``.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine

from tests.fixtures.doubles import (
    FakeClock,
    FakeJobQueue,
    FakeSpeechToText,
    FakeVideoProbe,
    InMemoryStorage,
)
from tests.fixtures.providers import MODAL_ENV, REGISTRY_TOML, FakeQueueHeartbeats
from tests.integration.api.batch_helpers import (
    HEADER,
    csv_bytes,
    new_batch,
    people,
    post_action,
    row_ids,
    set_batch,
    set_rows,
    usable_template,
)
from tests.integration.api.conftest import Env, make_settings
from vidgen.api.app import create_app
from vidgen.api.deps import AppDeps

LOCAL_QUEUE = "vidgen.local-mac"
MODAL_QUEUE = "vidgen.modal-demo"


def build_env(
    db: Engine,
    test_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    alive: set[str] | None = None,
    toml: str = REGISTRY_TOML,
    modal_env: bool = True,
    **overrides: Any,
) -> Env:
    """A logged-in app with the registry ``toml``; ``alive`` = queues with a running worker."""
    path = tmp_path / "providers.toml"
    path.write_text(toml, encoding="utf-8")
    for name, value in MODAL_ENV.items():
        if modal_env:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)
    settings = make_settings(test_db_url, tmp_path, providers_file=path, **overrides)
    clock, storage, queue = FakeClock(), InMemoryStorage(), FakeJobQueue()
    probe, stt = FakeVideoProbe(), FakeSpeechToText()
    heartbeats = FakeQueueHeartbeats(alive if alive is not None else {LOCAL_QUEUE, MODAL_QUEUE})
    deps = AppDeps(
        clock=clock,
        speech_to_text=stt,
        video_probe=probe,
        storage=storage,
        job_queue=queue,
        queue_heartbeats=heartbeats,  # type: ignore[call-arg]
    )
    app = create_app(settings, deps=deps)
    env = Env(app, TestClient(app), settings, clock, storage, probe, stt, queue, {}, deps)
    assert env.login().status_code == 200
    env.heartbeats = heartbeats  # type: ignore[attr-defined]
    return env


def create_with_class(
    env: Env,
    *,
    data_class: str | None = None,
    confirm_demo: str | None = None,
    template_id: str | None = None,
    count: int = 3,
) -> Response:
    """POST /batches with the new ``data_class`` / ``confirm_demo`` form fields."""
    data: dict[str, str] = {
        "template_id": template_id or usable_template(env),
        "name_column": "Name",
        "id_column": "ID",
    }
    if data_class is not None:
        data["data_class"] = data_class
    if confirm_demo is not None:
        data["confirm_demo"] = confirm_demo
    body = csv_bytes([list(HEADER), *people(count)])
    return env.client.post(
        "/batches",
        files={"sheet": ("sheet.csv", body, "application/octet-stream")},
        data=data,
        headers=env.csrf,
    )


def demo_batch(env: Env, count: int = 3) -> str:
    """A demo-data batch (confirmed)."""
    response = create_with_class(env, data_class="demo", confirm_demo="true", count=count)
    assert response.status_code == 201, response.text
    batch_id: str = response.json()["id"]
    return batch_id


def render_preview(env: Env, batch_id: str) -> None:
    """Request the preview and let the 'worker' finish it (no approval)."""
    assert post_action(env, batch_id, "preview").status_code == 202
    key = env.storage.write(f"previews/{batch_id}.mp4", io.BytesIO(b"PREVIEW-BYTES"))
    env.app.state.container.batches.preview_rendered(UUID(batch_id), key)


def approve_with(env: Env, batch_id: str, provider_id: str | None) -> Response:
    """POST preview/approve with an optional provider choice (preview must be rendered)."""
    body = None if provider_id is None else {"provider_id": provider_id}
    return env.client.post(f"/batches/{batch_id}/preview/approve", json=body, headers=env.csrf)


def start_batch(env: Env, batch_id: str, key: str = "k-1") -> Response:
    """POST start with an idempotency key."""
    headers = {**env.csrf, "Idempotency-Key": key}
    return env.client.post(f"/batches/{batch_id}/start", json={}, headers=headers)


def providers_of(env: Env, batch_id: str) -> dict[str, Any]:
    """GET /batches/{id}/providers."""
    response = env.client.get(f"/batches/{batch_id}/providers")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def listed(env: Env, batch_id: str, provider_id: str) -> dict[str, Any]:
    """One provider entry of the chooser list."""
    (item,) = [p for p in providers_of(env, batch_id)["providers"] if p["id"] == provider_id]
    return item  # type: ignore[no-any-return]


def started_with(env: Env, provider_id: str | None, *, demo: bool = True) -> str:
    """A batch approved with ``provider_id`` and started; the queue double is cleared after."""
    batch_id = demo_batch(env) if demo else new_batch(env)
    render_preview(env, batch_id)
    assert approve_with(env, batch_id, provider_id).status_code == 200
    assert start_batch(env, batch_id).status_code == 200
    return batch_id


def add_measured_runs(
    env: Env,
    db: Engine,
    provider_id: str,
    *,
    seconds: float = 100.0,
    cost: float = 0.1,
    count: int = 3,
    status: str = "COMPLETED",
) -> str:
    """A batch that ``provider_id`` rendered: ``count`` rows with a time and a cost."""
    batch_id = new_batch(env, people(count))
    set_batch(db, batch_id, provider_id=provider_id, status="COMPLETED")
    set_rows(
        db,
        batch_id,
        list(row_ids(db, batch_id)),
        status=status,
        render_seconds=seconds,
        cost_usd=cost,
    )
    return batch_id
