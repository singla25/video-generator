"""Full-stack fixture: real app, real Postgres test DB, real FFmpeg, real local storage.

Only the AI parts are fake (speech-to-text, voice, lip sync, quality check). The queue is
Dramatiq on an in-process StubBroker with a worker thread in the same process (no Redis).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dramatiq
import pytest
from dramatiq import Worker
from dramatiq.brokers.stub import StubBroker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from tests.fixtures.assets import devanagari_font, latin_font
from tests.fixtures.doubles import FakeClock, FakeSpeechToText, word
from tests.fixtures.pipeline_fakes import FakeLipSync, FakeQuality, FakeVoice
from tests.fixtures.templates import make_template
from tests.integration.api.conftest import PASSWORD, make_settings
from tests.integration.conftest import db, db_engine, test_db_url  # noqa: F401
from vidgen.api.app import create_app
from vidgen.api.container import AppDeps
from vidgen.domain.retry import WorkerCrashedError
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder
from vidgen.infrastructure.ffmpeg.label import PillowLabelRenderer
from vidgen.infrastructure.queue.dramatiq_queue import DramatiqJobQueue
from vidgen.infrastructure.storage.local import LocalStorage
from vidgen.services.render_row import RenderConfig, RowRenderer
from vidgen.settings import Settings
from vidgen.worker.actors import WorkerConfig, register_actors

QUEUE = "vidgen-e2e"


class ArmedCrashEncoder:
    """Wraps the real engine; once armed, the next render raises a worker crash."""

    def __init__(self, inner: FfmpegVideoEncoder) -> None:
        self._inner = inner
        self.armed = False
        self.calls = 0

    def render(self, *args: Any, **kwargs: Any) -> None:
        """Delegate to the real engine unless armed to crash."""
        self.calls += 1
        if self.armed:
            self.armed = False
            raise WorkerCrashedError
        self._inner.render(*args, **kwargs)


@dataclass
class Stack:
    """Everything an end-to-end test touches."""

    app: FastAPI
    client: TestClient
    settings: Settings
    clock: FakeClock
    media_root: Path
    broker: StubBroker
    encoder: ArmedCrashEncoder
    voice: FakeVoice
    stt: FakeSpeechToText
    template_video: Path
    csrf: dict[str, str]

    def wait_idle(self, timeout_ms: int = 60_000) -> None:
        """Block until the worker has handled every queued message (including retries)."""
        self.broker.join(QUEUE, timeout=timeout_ms)


@pytest.fixture
def stack(db: Engine, test_db_url: str, tmp_path: Path) -> Iterator[Stack]:  # noqa: F811
    """Build the whole stack and start an in-process worker."""
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for the end-to-end tests"
    media_root = tmp_path / "media"
    settings = make_settings(test_db_url, tmp_path, storage_root=media_root)
    clock = FakeClock()
    storage = LocalStorage(media_root)
    stt = FakeSpeechToText([word("Krishan", 1.0)])
    broker = StubBroker()
    broker.emit_after("process_boot")
    previous = dramatiq.get_broker()
    dramatiq.set_broker(broker)
    queue = DramatiqJobQueue(broker, queue_name=QUEUE)
    app = create_app(
        settings,
        deps=AppDeps(clock=clock, speech_to_text=stt, storage=storage, job_queue=queue),
    )
    voice = FakeVoice()
    voice.seconds = 0.5
    encoder = ArmedCrashEncoder(
        FfmpegVideoEncoder(ffmpeg_path=ffmpeg, timeout_seconds=120.0, crossfade_ms=30)
    )
    renderer = RowRenderer(
        session_factory=sessionmaker(db, expire_on_commit=False),
        storage=storage,
        cipher=AesGcmCipher(
            keys={settings.encryption_key_id: settings.encryption_key_bytes()},
            active_key_id=settings.encryption_key_id,
            index_key=settings.index_key_bytes(),
        ),
        voice=voice,
        lipsync=FakeLipSync(),
        encoder=encoder,
        quality=FakeQuality(),
        labels=PillowLabelRenderer(devanagari_font=devanagari_font(), latin_font=latin_font()),
        clock=clock,
        config=RenderConfig(creator_entity=settings.creator_entity, pause_s=0.6),
        preview_sink=app.state.container.batches,
    )
    register_actors(broker, renderer, WorkerConfig(queue_name=QUEUE, retry_delay_ms=50))
    worker = Worker(broker, worker_timeout=50, worker_threads=2)
    worker.start()
    client = TestClient(app)
    template_video = make_template(tmp_path / "template.mp4")
    response = client.post("/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    try:
        yield Stack(
            app, client, settings, clock, media_root, broker, encoder, voice, stt, template_video,
            {"X-CSRF-Token": response.json()["csrf_token"]},
        )  # fmt: skip
    finally:
        worker.stop()
        broker.flush_all()
        broker.close()
        dramatiq.set_broker(previous)
