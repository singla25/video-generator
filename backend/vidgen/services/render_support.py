"""Building blocks of the render pipeline: configuration, outcome, stage timing, helpers."""

from __future__ import annotations

import array
import logging
import math
import struct
import time
import wave
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.outcomes import RowOutcomeKind
from vidgen.domain.retry import FailureKind, RetryPolicy, classify_exception, failure_code_for
from vidgen.domain.timing import TimingRules
from vidgen.logging import log_event
from vidgen.ports.progress import StageReporter
from vidgen.ports.rows import RowJob

logger = logging.getLogger(__name__)

PREVIEW_KEY = "previews/{batch_id}.mp4"
MANIFEST_NAME = "manifest.csv"
WAV_CHUNK_FRAMES = 16384
BAND_ROUNDING_TOLERANCE = 1e-9  # keeps 1300 * 0.10 at 130, not 131
SECONDS_DIGITS = 6  # slot lengths are rounded to microseconds to avoid float noise
STAGE_PUBLISH = "publish"
KIND_BY_DOMAIN_CODE = {
    FailureCode.RENDER_TIMEOUT: FailureKind.TIMEOUT,
    FailureCode.STORAGE_ERROR: FailureKind.STORAGE,
}


LABEL_STYLES = ("bubble", "band")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    """One PNG chunk: length, type, data and the CRC of type and data."""
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _transparent_png(width: int, height: int) -> bytes:
    """A PNG of ``width`` x ``height`` pixels, all RGBA (0, 0, 0, 0): fully transparent."""
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA, no filters
    row = b"\x00" + b"\x00\x00\x00\x00" * width  # filter type 0, then transparent pixels
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(row * height))
        + _png_chunk(b"IEND", b"")
    )


# The label of every encode pass except the first: invisible, so only the first pass shows a label
TRANSPARENT_PNG: bytes = _transparent_png(1, 1)


@dataclass(frozen=True)
class RenderConfig:
    """Everything configurable about rendering a row."""

    creator_entity: str
    pause_s: float  # DD-7: the pause after the name; per-template measurement comes later
    timing: TimingRules = field(default_factory=TimingRules)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    label_band_share: float = 0.10  # share of the frame height covered by the AI label (C2)
    stale_margin_s: float = 60.0  # a PROCESSING row older than timeout + margin is abandoned
    label_style: str = "bubble"  # "bubble" (corner badge) or "band" (top band), DD-32
    name_gap_s: float = 0.0  # DD-34: extra silence and held frame after the new name
    spoken_suffix: str = ""  # DD-39: honorific spoken after the name; "" speaks the name only

    def __post_init__(self) -> None:
        if self.label_style not in LABEL_STYLES:
            raise ValueError(f"unknown label_style {self.label_style!r}; use one of {LABEL_STYLES}")

    @property
    def stale_after(self) -> timedelta:
        """How long a PROCESSING row may run before another worker takes it over."""
        return timedelta(seconds=self.retry.timeout_seconds + self.stale_margin_s)


@dataclass(frozen=True)
class RowOutcome:
    """What a delivery of a row job led to; ``delay_s`` tells when to deliver again."""

    kind: RowOutcomeKind
    code: FailureCode | None = None
    delay_s: float = 0.0


def report_stage(reporter: StageReporter | None, batch_id: UUID, stage: str) -> None:
    """Tell the progress store a preview entered ``stage``; errors never fail the render."""
    if reporter is None:
        return
    try:
        reporter.report(batch_id, stage)
    except Exception as exc:
        logger.warning(
            "preview stage not reported",
            extra={"stage": stage, "batch_id": str(batch_id), "error_type": type(exc).__name__},
        )


def clear_stage(reporter: StageReporter | None, batch_id: UUID) -> None:
    """Remove the progress entry of a finished preview; a failure is logged, not raised."""
    if reporter is None:
        return
    try:
        reporter.clear(batch_id)
    except Exception as exc:
        logger.warning(
            "preview stage not cleared",
            extra={"batch_id": str(batch_id), "error_type": type(exc).__name__},
        )


class Run:
    """One job's context: ids for logging, the stage that is running, and optional progress."""

    def __init__(self, job: RowJob, reporter: StageReporter | None = None) -> None:
        self.job = job
        self.stage_name = ""
        self._reporter = reporter

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Run a stage and log how long it took (also when it fails)."""
        self.stage_name = name
        report_stage(self._reporter, self.job.batch_id, name)
        started = time.perf_counter()
        try:
            yield
        finally:
            log_event(
                logger,
                "stage finished",
                level=logging.DEBUG,
                stage=name,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                row_id=self.job.row_id,
                batch_id=self.job.batch_id,
                attempt=self.job.attempts,
            )


def band_height(frame_height: int, share: float) -> int:
    """Height of the label band: ``share`` of the frame height, rounded up."""
    return math.ceil(frame_height * share - BAND_ROUNDING_TOLERANCE)


def classify_failure(exc: Exception, *, publishing: bool) -> tuple[FailureKind, FailureCode]:
    """Failure kind and stored code for an exception (B8, A4)."""
    if isinstance(exc, DomainError):
        return KIND_BY_DOMAIN_CODE.get(exc.code, FailureKind.QUALITY), exc.code
    kind = classify_exception(exc, during_output_write=publishing)
    return kind, failure_code_for(kind)


def is_silent(path: Path) -> bool:
    """True if a 16-bit PCM WAV file holds only zeros. Other files raise (the caller fails)."""
    with wave.open(str(path), "rb") as handle:
        chunks = iter(lambda: handle.readframes(WAV_CHUNK_FRAMES), b"")
        return not any(any(array.array("h", frames)) for frames in chunks)
