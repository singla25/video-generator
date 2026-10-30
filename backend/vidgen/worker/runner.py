"""Worker process: builds the renderer from settings and runs Dramatiq workers.

Process wiring only (exercised by the end-to-end run, not by unit tests):
``python -m vidgen.worker``.
"""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
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
from vidgen.infrastructure.db.uow import SqlUnitOfWork, get_engine, uow_factory
from vidgen.infrastructure.fakes import FakeQualityChecker
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder
from vidgen.infrastructure.ffmpeg.label import build_label_renderer
from vidgen.infrastructure.local_ai.factory import (
    build_ai_adapters,
    effective_worker_threads,
    log_startup_warning,
)
from vidgen.infrastructure.queue.dramatiq_queue import DramatiqJobQueue
from vidgen.infrastructure.queue.redis_heartbeat import HeartbeatLoop
from vidgen.infrastructure.storage.local import LocalStorage
from vidgen.logging import configure_logging
from vidgen.ports.rows import PreviewSink
from vidgen.services.render_row import RenderConfig, RowRenderer
from vidgen.services.requeue import requeue_stuck_rows
from vidgen.settings import Settings, get_settings
from vidgen.worker.actors import WorkerConfig, register_actors
from vidgen.worker.periodic import PeriodicTask

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
        label_style=settings.label_style,
        name_gap_s=settings.name_gap_s,
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
    """The row renderer; AI adapters follow ``ai_mode`` (fake or local), the engine is real."""
    if settings.ai_backend != "fake":
        raise RuntimeError("Real AI adapters arrive in M2; set VIDGEN_AI_MODE=local instead.")
    ai = build_ai_adapters(settings)
    factory = sessionmaker(get_engine(settings.database_url), expire_on_commit=False)
    cipher = AesGcmCipher(
        keys={settings.encryption_key_id: settings.encryption_key_bytes()},
        active_key_id=settings.encryption_key_id,
        index_key=settings.index_key_bytes(),
    )
    return RowRenderer(
        row_store_factory=lambda: SqlRowStore(factory, cipher),
        storage=LocalStorage(settings.storage_root),
        voice=ai.voice,
        lipsync=ai.lipsync,
        encoder=FfmpegVideoEncoder(
            ffmpeg_path=FFMPEG,
            timeout_seconds=settings.row_timeout_seconds,
            crossfade_ms=settings.crossfade_ms,
        ),
        quality=FakeQualityChecker(),
        labels=build_label_renderer(
            settings.label_style,
            devanagari_font=FONT_DIR / DEVANAGARI_FONT,
            latin_font=FONT_DIR / LATIN_FONT,
        ),
        clock=SystemClock(),
        config=render_config(settings),
        preview_sink=sink,
    )


def build_requeue_job(
    settings: Settings, broker: RedisBroker
) -> Callable[[], object]:  # pragma: no cover
    """The lost-message recovery pass, ready to run on a timer."""
    cipher = AesGcmCipher(
        keys={settings.encryption_key_id: settings.encryption_key_bytes()},
        active_key_id=settings.encryption_key_id,
        index_key=settings.index_key_bytes(),
    )
    factory = uow_factory(settings.database_url)
    queue = DramatiqJobQueue(broker, queue_name=settings.queue_name)
    clock = SystemClock()

    def job() -> object:
        return requeue_stuck_rows(
            lambda: SqlUnitOfWork(factory, cipher),
            queue,
            clock,
            stuck_after_seconds=settings.stuck_after_seconds,
        )

    return job


def run() -> None:  # pragma: no cover
    """Start the worker threads and wait for SIGINT or SIGTERM."""
    settings = get_settings()
    configure_logging()
    log_startup_warning(settings)
    broker = RedisBroker(url=settings.redis_url)  # type: ignore[no-untyped-call]
    dramatiq.set_broker(broker)
    sink = build_container(settings, AppDeps()).batches
    register_actors(broker, build_renderer(settings, sink), WorkerConfig.from_settings(settings))
    worker = Worker(broker, worker_threads=effective_worker_threads(settings))
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    beat = HeartbeatLoop(default_heartbeat(settings), settings.heartbeat_interval_seconds)
    worker.start()
    beat.start()
    recovery = PeriodicTask(build_requeue_job(settings, broker), settings.requeue_interval_seconds)
    recovery.start()
    try:
        stop.wait()
    finally:
        recovery.stop()
        beat.stop()
        worker.stop()
