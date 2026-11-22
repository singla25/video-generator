"""Chooses fake or local AI adapters from ``Settings.ai_mode`` (AC1, AC2, AC7, AC8)."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path

from vidgen.infrastructure.fakes import (
    FakeLipSyncer,
    FakeSpeechToText,
    FakeTransliterator,
    FakeVoiceCloner,
)
from vidgen.infrastructure.local_ai.guard import SingleRenderGuard
from vidgen.infrastructure.local_ai.lipsync import MuseTalkLipSyncer
from vidgen.infrastructure.local_ai.stt import FasterWhisperSpeechToText
from vidgen.infrastructure.local_ai.transliterate import QwenTransliterator
from vidgen.infrastructure.local_ai.tts import ChatterboxVoiceCloner
from vidgen.ports import LipSyncer, SpeechToText, Transliterator, VoiceCloner
from vidgen.ports.warmup import Warmable
from vidgen.settings import Settings

logger = logging.getLogger(__name__)

LOCAL_WORKER_THREADS = 1
MIN_LABEL_SHARE = 0.10  # C2: the AI label covers at least 10 % of the frame height
ROUNDING_TOLERANCE = 1e-9
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "PYTORCH_ENABLE_MPS_FALLBACK": "1",
}
LEGACY_WHISPER_DIR = "whisper"
WHISPER_DIRS = {"small": "whisper-small", "medium": "whisper-medium"}
QWEN_DIR, CHATTERBOX_DIR, MUSETALK_DIR = "qwen", "chatterbox", "musetalk"
FAKE_BANNER = "Fake AI: beep stands in"
LOCAL_BANNER = "Local AI"
UNVERIFIED_WEIGHTS = (
    "S3FD face-detector weights (no licence stated)",
    "face-parse-bisent weights (no terms; research-oriented training data)",
)


def whisper_weights_dir(weights_root: Path, size: str) -> Path:
    """Folder holding the Whisper weights for ``size``; creates nothing.

    ``small`` falls back to the legacy ``whisper`` folder when ``whisper-small`` is absent.
    """
    name = WHISPER_DIRS.get(size)
    if name is None:
        raise ValueError(f"unknown whisper size {size!r}; use one of {sorted(WHISPER_DIRS)}")
    folder = weights_root / name
    if size == "small" and not folder.exists():
        return weights_root / LEGACY_WHISPER_DIR
    return folder


@dataclass(frozen=True)
class AiAdapters:
    """The four AI ports for the chosen mode."""

    stt: SpeechToText
    transliterator: Transliterator
    voice: VoiceCloner
    lipsync: LipSyncer


def build_ai_adapters(settings: Settings) -> AiAdapters:
    """Fake adapters, or real ones that load their models lazily on first use."""
    if settings.ai_mode == "fake":
        return AiAdapters(
            stt=FakeSpeechToText(),
            transliterator=FakeTransliterator(),
            voice=FakeVoiceCloner(),
            lipsync=FakeLipSyncer(),
        )
    os.environ.update(OFFLINE_ENV)
    root = settings.local_ai_weights_dir
    return AiAdapters(
        stt=FasterWhisperSpeechToText(whisper_weights_dir(root, settings.whisper_size)),
        transliterator=QwenTransliterator(root / QWEN_DIR),
        voice=ChatterboxVoiceCloner(root / CHATTERBOX_DIR),
        lipsync=MuseTalkLipSyncer(root / MUSETALK_DIR, guard=SingleRenderGuard()),
    )


def warmable_adapters(adapters: AiAdapters) -> list[Warmable]:
    """The adapters that load a model of their own (speech, voice, lip sync), in that order."""
    candidates: tuple[object, ...] = (adapters.stt, adapters.voice, adapters.lipsync)
    return [adapter for adapter in candidates if isinstance(adapter, Warmable)]


def effective_worker_threads(settings: Settings) -> int:
    """One thread in local mode (the models need the memory); otherwise the configured count."""
    return LOCAL_WORKER_THREADS if settings.ai_mode == "local" else settings.worker_threads


def describe_mode(settings: Settings) -> str:
    """Short text for the UI banner."""
    return LOCAL_BANNER if settings.ai_mode == "local" else FAKE_BANNER


def log_startup_warning(settings: Settings) -> None:
    """In local mode, warn that two lip-sync weights have unverified licences (ADR-012)."""
    if settings.ai_mode == "local":
        logger.warning(
            "local AI mode: development use only until licences are verified",
            extra={"unverified_weights": list(UNVERIFIED_WEIGHTS)},
        )


def local_label_band_height(settings: Settings, frame_h: int) -> int:
    """Label band height for the local pipeline: 0 for the bubble, else >= 10 %."""
    if settings.label_style == "bubble":
        return 0
    share = max(settings.label_band_share, MIN_LABEL_SHARE)
    return math.ceil(frame_h * share - ROUNDING_TOLERANCE)
