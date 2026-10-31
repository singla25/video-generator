"""GET /batches/{id} reports the preview stage while the preview is rendering (T-PROG-BE, item 5).

CONTRACT
  AppDeps gains ``stage_reporter`` (a StageReporter). The batch JSON ``preview`` object gains
  ``stage``: while the preview status is PENDING it is "preparing" (fetch, or no stage yet),
  "voice" (tts), "lipsync" (lipsync), "finishing" (encode, check, publish); unknown raw stage
  -> "preparing". Otherwise (READY, FAILED, no preview) it is null.
Assumption (flagged): a failing reporter read never breaks the batch page; the stage is then
"preparing" and the response is still 200 without the Redis error text.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine

from tests.fixtures.doubles import (
    FakeClock,
    FakeJobQueue,
    FakeSpeechToText,
    FakeStageReporter,
    FakeVideoProbe,
    InMemoryStorage,
)
from tests.integration.api.batch_helpers import get_batch, new_batch, post_action
from tests.integration.api.conftest import Env, make_settings
from vidgen.api.app import create_app
from vidgen.api.deps import AppDeps
from vidgen.domain.codes import FailureCode


@pytest.fixture
def reporter() -> FakeStageReporter:
    """The stage reporter the app reads from (the test writes the worker's stages into it)."""
    return FakeStageReporter()


@pytest.fixture
def staged_env(
    db: Engine, test_db_url: str, tmp_path: Path, reporter: FakeStageReporter
) -> Iterator[Env]:
    """A logged-in app that uses the fake reporter instead of Redis."""
    settings = make_settings(test_db_url, tmp_path)
    clock, storage = FakeClock(), InMemoryStorage()
    probe, stt, queue = FakeVideoProbe(), FakeSpeechToText(), FakeJobQueue()
    deps = AppDeps(
        clock=clock,
        speech_to_text=stt,
        video_probe=probe,
        storage=storage,
        job_queue=queue,
        stage_reporter=reporter,
    )
    app = create_app(settings, deps=deps)
    env = Env(app, TestClient(app), settings, clock, storage, probe, stt, queue, csrf={}, deps=deps)
    assert env.login().status_code == 200
    yield env


def request_preview(env: Env) -> str:
    """A batch with a requested (PENDING) preview; returns the batch id."""
    batch_id = new_batch(env)
    assert post_action(env, batch_id, "preview").status_code == 202
    return batch_id


def preview_of(env: Env, batch_id: str) -> dict[str, Any]:
    """The ``preview`` object of GET /batches/{id}."""
    preview: dict[str, Any] = get_batch(env, batch_id)["preview"]
    return preview


def finish_preview(env: Env, batch_id: str) -> None:
    """Let the worker report the preview as rendered (the same hook the worker calls)."""
    key = env.storage.write(f"previews/{batch_id}.mp4", io.BytesIO(b"PREVIEW-BYTES"))
    env.app.state.container.batches.preview_rendered(UUID(batch_id), key)


def fail_preview(env: Env, batch_id: str) -> None:
    """Let the worker report the preview as failed (the same hook the worker calls)."""
    env.app.state.container.batches.preview_failed(UUID(batch_id), FailureCode.TTS_FAILED)


# ---- positive ----------------------------------------------------------------------------

PENDING_TABLE = [
    ("fetch", "preparing"),
    ("tts", "voice"),
    ("lipsync", "lipsync"),
    ("encode", "finishing"),
    ("check", "finishing"),
    ("publish", "finishing"),
]


@pytest.mark.parametrize(("raw", "label"), PENDING_TABLE)
def test_pending_preview_shows_the_label_for_its_raw_stage(
    staged_env: Env, reporter: FakeStageReporter, raw: str, label: str
) -> None:
    """P1: the mapping table from the contract."""
    batch_id = request_preview(staged_env)
    reporter.report(UUID(batch_id), raw)
    preview = preview_of(staged_env, batch_id)
    assert preview["status"] == "PENDING"
    assert preview["stage"] == label


def test_pending_preview_without_any_stage_yet_is_preparing(staged_env: Env) -> None:
    """P2: the worker has not started yet, so there is no stage."""
    batch_id = request_preview(staged_env)
    assert preview_of(staged_env, batch_id)["stage"] == "preparing"


def test_stage_follows_the_reporter_as_the_render_moves_on(
    staged_env: Env, reporter: FakeStageReporter
) -> None:
    """P4: each poll shows the latest stage."""
    batch_id = request_preview(staged_env)
    reporter.report(UUID(batch_id), "tts")
    assert preview_of(staged_env, batch_id)["stage"] == "voice"
    reporter.report(UUID(batch_id), "lipsync")
    assert preview_of(staged_env, batch_id)["stage"] == "lipsync"


def test_stage_key_is_present_in_the_fake_mode_preview_body(staged_env: Env) -> None:
    """P3: fake mode returns a short preview body; ``stage`` must be part of it too."""
    batch_id = request_preview(staged_env)
    preview = preview_of(staged_env, batch_id)
    assert set(preview) == {"status", "approved", "stage"}


# ---- negative ----------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["mystery", "", "voice"])
def test_unknown_raw_stage_is_preparing(
    staged_env: Env, reporter: FakeStageReporter, raw: str
) -> None:
    """N1: anything that is not a raw stage name (including a label) reads as preparing."""
    batch_id = request_preview(staged_env)
    reporter.report(UUID(batch_id), raw)
    assert preview_of(staged_env, batch_id)["stage"] == "preparing"


def test_a_failing_stage_read_is_still_200_preparing_and_leaks_no_secret(
    staged_env: Env, reporter: FakeStageReporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N2/N3: Redis down while reading the stage does not break the batch page (assumption)."""
    batch_id = request_preview(staged_env)

    def redis_down(batch: UUID) -> str | None:
        raise RedisConnectionError(
            "Error 111 connecting to redis://:s3cret-redis-pw@redis-host:6379/0"
        )

    monkeypatch.setattr(reporter, "current", redis_down)
    response = staged_env.client.get(f"/batches/{batch_id}")
    assert response.status_code == 200
    assert response.json()["preview"]["stage"] == "preparing"
    assert "s3cret-redis-pw" not in response.text


# ---- edge --------------------------------------------------------------------------------


@pytest.mark.parametrize("settle", [finish_preview, fail_preview], ids=["ready", "failed"])
def test_a_settled_preview_has_no_stage_even_if_one_is_still_stored(
    staged_env: Env, reporter: FakeStageReporter, settle: Any
) -> None:
    """E1/E2: READY and FAILED give null, whatever the reporter still holds."""
    batch_id = request_preview(staged_env)
    reporter.report(UUID(batch_id), "tts")
    settle(staged_env, batch_id)
    preview = preview_of(staged_env, batch_id)
    assert preview["status"] in {"READY", "FAILED"}
    assert preview["stage"] is None


def test_a_batch_without_a_preview_has_no_stage(
    staged_env: Env, reporter: FakeStageReporter
) -> None:
    """E3: a DRAFT that never asked for a preview has null, even with a stale stage stored."""
    batch_id = new_batch(staged_env)
    reporter.report(UUID(batch_id), "tts")
    preview = preview_of(staged_env, batch_id)
    assert preview["status"] == "NONE"
    assert preview["stage"] is None


def test_stages_of_two_batches_do_not_leak_into_each_other(
    staged_env: Env, reporter: FakeStageReporter
) -> None:
    """E5: only the batch's own stage is shown."""
    first = request_preview(staged_env)
    second = request_preview(staged_env)
    reporter.report(UUID(first), "encode")
    assert preview_of(staged_env, first)["stage"] == "finishing"
    assert preview_of(staged_env, second)["stage"] == "preparing"
