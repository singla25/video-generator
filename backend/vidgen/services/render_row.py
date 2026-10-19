"""The per-row render pipeline (AC8-AC12, AC17, AC18, C1-C3, D16, DD-6).

Stages: tts -> lipsync -> encode -> check -> publish. Rows are claimed with a row lock, so two
workers never render one row twice. Failures are classified (B8): crashes, timeouts and
storage errors get one automatic retry, everything else is final. Personal data lives only in
local variables of one job; logs carry ids, codes and timings (C5).
"""

from __future__ import annotations

import array
import io
import logging
import math
import time
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.naming import output_file_name
from vidgen.domain.outcomes import RowOutcomeKind
from vidgen.domain.retry import FailureKind, RetryPolicy, classify_exception, failure_code_for
from vidgen.domain.timing import TimingRules, plan_timing
from vidgen.domain.validation import effective_spoken_name
from vidgen.logging import log_event
from vidgen.ports import (
    Clock,
    LabelRenderer,
    LipSyncer,
    QualityChecker,
    Storage,
    VideoEncoder,
    VoiceCloner,
)
from vidgen.ports.rows import (
    ClaimDecision,
    ClaimSnapshot,
    ManifestInput,
    PreviewSink,
    RowJob,
    RowStore,
    RowUpdate,
)
from vidgen.services.claim_rules import decide_claim, decide_completion
from vidgen.services.manifest import build_manifest_csv, manifest_row

__all__ = ["RenderConfig", "RowOutcome", "RowOutcomeKind", "RowRenderer"]

logger = logging.getLogger(__name__)

PREVIEW_KEY = "previews/{batch_id}.mp4"
MANIFEST_NAME = "manifest.csv"
WAV_CHUNK_FRAMES = 16384
BAND_ROUNDING_TOLERANCE = 1e-9  # keeps 1300 * 0.10 at 130, not 131
SECONDS_DIGITS = 6  # slot lengths are rounded to microseconds to avoid float noise
STAGE_PUBLISH = "publish"
_KIND_BY_DOMAIN_CODE = {
    FailureCode.RENDER_TIMEOUT: FailureKind.TIMEOUT,
    FailureCode.STORAGE_ERROR: FailureKind.STORAGE,
}


@dataclass(frozen=True)
class RenderConfig:
    """Everything configurable about rendering a row."""

    creator_entity: str
    pause_s: float  # DD-7: the pause after the name; per-template measurement comes later
    timing: TimingRules = field(default_factory=TimingRules)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    label_band_share: float = 0.10  # share of the frame height covered by the AI label (C2)
    stale_margin_s: float = 60.0  # a PROCESSING row older than timeout + margin is abandoned

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


class _Run:
    """One job's context: ids for logging and the stage that is currently running."""

    def __init__(self, job: RowJob) -> None:
        self.job = job
        self.stage_name = ""

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Run a stage and log how long it took (also when it fails)."""
        self.stage_name = name
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


def _band_height(frame_height: int, share: float) -> int:
    """Height of the label band: ``share`` of the frame height, rounded up."""
    return math.ceil(frame_height * share - BAND_ROUNDING_TOLERANCE)


def classify_failure(exc: Exception, *, publishing: bool) -> tuple[FailureKind, FailureCode]:
    """Failure kind and stored code for an exception (B8, A4)."""
    if isinstance(exc, DomainError):
        return _KIND_BY_DOMAIN_CODE.get(exc.code, FailureKind.QUALITY), exc.code
    kind = classify_exception(exc, during_output_write=publishing)
    return kind, failure_code_for(kind)


def _is_silent(path: Path) -> bool:
    """True if a 16-bit PCM WAV file holds only zeros. Other files raise (the caller fails)."""
    with wave.open(str(path), "rb") as handle:
        chunks = iter(lambda: handle.readframes(WAV_CHUNK_FRAMES), b"")
        return not any(any(array.array("h", frames)) for frames in chunks)


class RowRenderer:
    """Renders rows and previews; one instance serves many jobs and threads."""

    def __init__(
        self,
        *,
        row_store_factory: Callable[[], RowStore],
        storage: Storage,
        voice: VoiceCloner,
        lipsync: LipSyncer,
        encoder: VideoEncoder,
        quality: QualityChecker,
        labels: LabelRenderer,
        clock: Clock,
        config: RenderConfig,
        preview_sink: PreviewSink,
    ) -> None:
        self._store = row_store_factory()
        self._storage = storage
        self._voice = voice
        self._lipsync = lipsync
        self._encoder = encoder
        self._quality = quality
        self._labels = labels
        self._clock = clock
        self._config = config
        self._preview_sink = preview_sink

    # ---- rows --------------------------------------------------------------------------

    def render(self, batch_id: UUID, row_id: UUID) -> RowOutcome:
        """Handle one delivery of a row job."""
        config, started = self._config, self._clock.now()

        def decide(snapshot: ClaimSnapshot) -> ClaimDecision:
            return decide_claim(snapshot, started, config.stale_after)

        claim = self._store.claim(batch_id, row_id, decide, started)
        if claim.job is None:
            return RowOutcome(claim.outcome)
        run = _Run(claim.job)
        try:
            key = self._produce_output(run)
        except Exception as exc:
            kind, code = classify_failure(exc, publishing=run.stage_name == STAGE_PUBLISH)
            log_event(
                logger,
                "row failed",
                level=logging.WARNING,
                code=code.value,
                row_id=run.job.row_id,
                batch_id=batch_id,
                attempt=run.job.attempts,
            )
            retry = config.retry.should_retry(kind, run.job.attempts)
            update = RowUpdate("QUEUED") if retry else self._failed(code, started)
            outcome = (
                RowOutcome(RowOutcomeKind.RETRY, code, config.retry.delay_seconds)
                if retry
                else RowOutcome(RowOutcomeKind.FAILED, code)
            )
        else:
            update = RowUpdate("COMPLETED", output_key=key, render_seconds=self._elapsed(started))
            outcome = RowOutcome(RowOutcomeKind.COMPLETED)
        manifest = self._store.finish(
            batch_id, row_id, update, self._clock.now(), decide_completion
        )
        if manifest is not None:
            self._write_manifest(manifest)
        return outcome

    def _failed(self, code: FailureCode, started: datetime) -> RowUpdate:
        return RowUpdate("FAILED", failure_code=code.value, render_seconds=self._elapsed(started))

    def _elapsed(self, started: datetime) -> float:
        return (self._clock.now() - started).total_seconds()

    def _produce_output(self, run: _Run) -> str:
        """Render a claimed row and store its output; returns the storage key."""
        job = run.job
        if job.attempts > self._config.retry.total_attempts:
            raise DomainError(FailureCode.INTERNAL_ERROR)  # a worker died on every attempt
        self._ensure_allowed(job)
        key = f"{job.folder_name}/{output_file_name(job.voter_id)}"
        if self._storage.exists(key):
            return key  # the worker died after storing the file but before saving the status
        with self._video(run) as video, run.stage(STAGE_PUBLISH), video.open("rb") as handle:
            return self._storage.write(key, handle)

    def _write_manifest(self, data: ManifestInput) -> None:
        """Write (replace) manifest.csv in the batch folder; a failure never fails the row."""
        key = f"{data.folder_name}/{MANIFEST_NAME}"
        text = build_manifest_csv(manifest_row(r) for r in data.rows)
        try:
            self._storage.delete(key)
            self._storage.write(key, io.BytesIO(text.encode("utf-8")))
        except DomainError as exc:
            log_event(logger, "manifest not written", level=logging.ERROR, code=exc.code.value)

    # ---- previews ----------------------------------------------------------------------

    def render_preview(self, batch_id: UUID, row_id: UUID, attempt: int = 1) -> RowOutcome:
        """Render the preview of a row into the preview location and report the result."""
        job = self._store.preview_job(batch_id, row_id)
        if job is None:
            return RowOutcome(RowOutcomeKind.NOOP)
        run = _Run(job)
        try:
            self._ensure_allowed(job)
            key = PREVIEW_KEY.format(batch_id=batch_id)
            with self._video(run) as video, run.stage(STAGE_PUBLISH), video.open("rb") as handle:
                self._storage.delete(key)  # a new preview replaces the old one
                stored = self._storage.write(key, handle)
        except Exception as exc:
            kind, code = classify_failure(exc, publishing=run.stage_name == STAGE_PUBLISH)
            if self._config.retry.should_retry(kind, attempt):
                return RowOutcome(RowOutcomeKind.RETRY, code, self._config.retry.delay_seconds)
            self._preview_sink.preview_failed(batch_id, code)
            return RowOutcome(RowOutcomeKind.FAILED, code)
        self._preview_sink.preview_rendered(batch_id, stored)
        return RowOutcome(RowOutcomeKind.COMPLETED)

    # ---- pipeline ----------------------------------------------------------------------

    @staticmethod
    def _ensure_allowed(job: RowJob) -> None:
        """Consent and a confirmed slot are required before any work (C1, C6)."""
        if not job.template.consent_confirmed:
            raise DomainError(FailureCode.CONSENT_MISSING)
        if not job.template.slot_confirmed or job.template.slot is None:
            raise DomainError(FailureCode.CONTENT_LOCK_VIOLATION)

    @contextmanager
    def _video(self, run: _Run) -> Iterator[Path]:
        """Produce the finished video in a temporary folder that is always removed."""
        with TemporaryDirectory(prefix="vidgen-row-") as folder:
            yield self._produce_video(run, Path(folder))

    def _produce_video(self, run: _Run, folder: Path) -> Path:
        """tts -> lipsync -> encode -> check. Returns the path of the checked output."""
        job = run.job
        slot = job.template.slot
        assert slot is not None  # noqa: S101 - guaranteed by _ensure_allowed
        template = folder / "template.mp4"
        with run.stage("fetch"), self._storage.open(job.template.video_key) as source:
            template.write_bytes(source.read())
        speech = folder / "speech.wav"
        with run.stage("tts"):
            seconds = self._synthesize(
                effective_spoken_name(job.name, job.spoken_name), template, speech
            )
        plan = plan_timing(
            round(slot[1] - slot[0], SECONDS_DIGITS),
            self._config.pause_s,
            seconds,
            self._config.timing,
        )
        synced = folder / "lipsync.mp4"
        with run.stage("lipsync"):
            self._lipsync.sync(template, speech, synced)
        label = folder / "label.png"
        self._labels.render_label(
            job.template.width,
            _band_height(job.template.height, self._config.label_band_share),
            label,
        )
        output = folder / "output.mp4"
        metadata = {
            "creator_entity": self._config.creator_entity,
            "generated_on": self._clock.now().date().isoformat(),
            "batch_id": str(job.batch_id),
        }
        with run.stage("encode"):
            self._encoder.render(synced, speech, slot, plan, label, metadata, output)
        with run.stage("check"):
            if self._quality.check(template, output):
                raise DomainError(FailureCode.OUTPUT_CHECK_FAILED)
        return output

    def _synthesize(self, text: str, sample: Path, out: Path) -> float:
        """Create the new speech; an error, zero length or silence is TTS_FAILED (B2)."""
        try:
            seconds = self._voice.synthesize(text, sample, out)
            unusable = seconds <= 0 or _is_silent(out)
        except Exception as exc:
            raise DomainError(FailureCode.TTS_FAILED) from exc
        if unusable:
            raise DomainError(FailureCode.TTS_FAILED)
        return seconds
