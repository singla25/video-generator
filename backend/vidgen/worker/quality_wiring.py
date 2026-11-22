"""Worker builders for the output quality checker and the temp-file cleanup (BL-14)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from vidgen.infrastructure.fakes import FakeQualityChecker
from vidgen.infrastructure.ffmpeg.quality import OutputQualityChecker
from vidgen.infrastructure.storage.local import LocalStorage
from vidgen.ports.interfaces import QualityChecker
from vidgen.settings import Settings

FFMPEG = "ffmpeg"
logger = logging.getLogger(__name__)


def build_quality_checker(settings: Settings) -> QualityChecker:
    """The real checker for local and modal modes; the fake only in fake mode."""
    if settings.ai_mode == "fake":
        return FakeQualityChecker()
    return OutputQualityChecker(
        ffmpeg_path=FFMPEG,
        timeout_seconds=settings.row_timeout_seconds,
        duration_tolerance_ms=settings.duration_tolerance_ms,
        loudness_tolerance_lu=settings.loudness_tolerance_lu,
    )


def build_temp_cleanup_job(settings: Settings) -> Callable[[], int]:
    """A pass that removes stale ``.tmp-*`` files from storage; returns how many it removed."""
    storage = LocalStorage(settings.storage_root)
    max_age = timedelta(seconds=settings.temp_max_age_seconds)

    def job() -> int:
        removed = storage.remove_stale_temp(max_age)
        if removed:
            logger.info("stale temp files removed", extra={"count": removed})
        return removed

    return job
