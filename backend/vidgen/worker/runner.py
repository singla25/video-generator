"""Worker process: builds the renderer from settings and runs Dramatiq workers.

Process wiring only (exercised by the end-to-end run, not by unit tests):
``python -m vidgen.worker``.
"""

from __future__ import annotations

import signal
import threading
from pathlib import Path

import dramatiq
from dramatiq import Worker
from dramatiq.brokers.redis import RedisBroker
from sqlalchemy.orm import sessionmaker

import vidgen
from vidgen.api.container import AppDeps, build_container, default_heartbeat
from vidgen.domain.retry import RetryPolicy
from vidgen.domain.timing import TimingRules
from vidgen.infrastructure.clock import SystemClock
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.db.row_store import SqlRowStore
from vidgen.infrastructure.db.uow import get_engine
from vidgen.infrastructure.fakes import FakeLipSyncer, FakeQualityChecker, FakeVoiceCloner
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder
from vidgen.infrastructure.ffmpeg.label import PillowLabelRenderer
from vidgen.infrastructure.queue.redis_heartbeat import HeartbeatLoop
from vidgen.infrastructure.storage.local import LocalStorage
from vidgen.logging import configure_logging
from vidgen.ports.rows import PreviewSink
from vidgen.services.render_row import RenderConfig, RowRenderer
from vidgen.settings import Settings, get_settings
from vidgen.worker.actors import WorkerConfig, register_actors

FONT_DIR = Path(vidgen.__file__).parent / "assets" / "fonts"
DEVANAGARI_FONT = "NotoSansDevanagari-Bold.ttf"
LATIN_FONT = "NotoSans-Bold.ttf"
FFMPEG = "ffmpeg"


def render_config(settings: Settings) -> RenderConfig:
    """Rendering options from settings."""
    return RenderConfig(
        creator_entity=settings.creator_entity,
        pause_s=settings.pause_seconds,
        label_band_share=settings.label_band_share,
        timing=TimingRules(
            max_stretch_ratio=settings.max_stretch_ratio,
            max_extension_s=settings.max_extension_seconds,
            crossfade_ms=settings.crossfade_ms,
        ),
        retry=RetryPolicy(
            timeout_seconds=settings.row_timeout_seconds,
            delay_seconds=settings.retry_delay_seconds,
            max_retries=settings.max_retries,
        ),
    )


def build_renderer(settings: Settings, sink: PreviewSink) -> RowRenderer:
    """The row renderer with fake AI adapters (``ai_backend=fake``) and the real engine."""
    if settings.ai_backend != "fake":
        raise RuntimeError("Real AI adapters arrive in M2; set VIDGEN_AI_BACKEND=fake.")
    factory = sessionmaker(get_engine(settings.database_url), expire_on_commit=False)
    cipher = AesGcmCipher(
        keys={settings.encryption_key_id: settings.encryption_key_bytes()},
        active_key_id=settings.encryption_key_id,
        index_key=settings.index_key_bytes(),
    )
    return RowRenderer(
        row_store_factory=lambda: SqlRowStore(factory, cipher),
        storage=LocalStorage(settings.storage_root),
        voice=FakeVoiceCloner(),
        lipsync=FakeLipSyncer(),
        encoder=FfmpegVideoEncoder(
            ffmpeg_path=FFMPEG,
            timeout_seconds=settings.row_timeout_seconds,
            crossfade_ms=settings.crossfade_ms,
        ),
        quality=FakeQualityChecker(),
        labels=PillowLabelRenderer(
            devanagari_font=FONT_DIR / DEVANAGARI_FONT, latin_font=FONT_DIR / LATIN_FONT
        ),
        clock=SystemClock(),
        config=render_config(settings),
        preview_sink=sink,
    )


def run() -> None:  # pragma: no cover
    """Start the worker threads and wait for SIGINT or SIGTERM."""
    settings = get_settings()
    configure_logging()
    broker = RedisBroker(url=settings.redis_url)  # type: ignore[no-untyped-call]
    dramatiq.set_broker(broker)
    sink = build_container(settings, AppDeps()).batches
    register_actors(broker, build_renderer(settings, sink), WorkerConfig.from_settings(settings))
    worker = Worker(broker, worker_threads=settings.worker_threads)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    beat = HeartbeatLoop(default_heartbeat(settings), settings.heartbeat_interval_seconds)
    worker.start()
    beat.start()
    try:
        stop.wait()
    finally:
        beat.stop()
        worker.stop()
