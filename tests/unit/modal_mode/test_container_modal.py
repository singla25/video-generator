"""AC4: the API container and the worker renderer build in modal mode without `modal`/tokens."""

from __future__ import annotations

import sys
from typing import Any

from tests.fixtures.doubles import FakeClock, FakeJobQueue, FakeStageReporter, InMemoryStorage
from tests.fixtures.providers import FakeQueueHeartbeats
from vidgen.api.container import AppDeps, build_container
from vidgen.infrastructure.modal_ai.stt import ModalSpeechToText
from vidgen.infrastructure.modal_ai.tts import ModalVoiceCloner


class _Beat:
    def beat(self) -> None:
        return None


def deps() -> AppDeps:
    return AppDeps(
        clock=FakeClock(),
        storage=InMemoryStorage(),
        job_queue=FakeJobQueue(),
        worker_heartbeat=_Beat(),  # type: ignore[arg-type]
        stage_reporter=FakeStageReporter(),
        queue_heartbeats=FakeQueueHeartbeats(),
        video_probe=object(),  # type: ignore[arg-type]
    )


def test_the_container_builds_in_modal_mode_without_modal_or_tokens(
    modal_settings: Any, without_modal: None
) -> None:
    container = build_container(modal_settings, deps())
    assert container.settings.ai_mode == "modal"
    assert sys.modules.get("modal") is None


def test_the_container_uses_the_modal_speech_to_text_in_modal_mode(
    modal_settings: Any, without_modal: None
) -> None:
    container = build_container(modal_settings, deps())
    assert isinstance(container.templates._stt, ModalSpeechToText)


def test_the_container_does_not_build_local_models_in_modal_mode(
    modal_settings: Any, without_modal: None
) -> None:
    build_container(modal_settings, deps())
    assert "faster_whisper" not in sys.modules
    assert "torch" not in sys.modules


def test_the_worker_renderer_uses_modal_voice_and_unavailable_lip_sync(
    modal_settings: Any, without_modal: None
) -> None:
    from vidgen.worker.runner import build_renderer

    renderer = build_renderer(modal_settings, sink=object())  # type: ignore[arg-type]
    assert isinstance(renderer._voice, ModalVoiceCloner)
    assert type(renderer._lipsync).__name__ == "UnavailableLipSyncer"
    assert sys.modules.get("modal") is None
