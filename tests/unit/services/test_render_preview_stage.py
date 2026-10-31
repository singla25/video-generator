"""Preview stage progress in the render service (T-PROG-BE, contract item 4).

CONTRACT
  RowRenderer(..., stage_reporter=None). A preview job reports the raw stage name of every
  ``run.stage(name)`` start for the preview's batch id, in the order fetch, tts, lipsync,
  encode, check, publish. After preview_rendered or preview_failed the reporter is cleared.
  Row jobs never report. A reporter that raises never fails the render; the error is logged.
Unit level: an in-memory row store and the pipeline fakes; no database, no network.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from tests.fixtures.doubles import FakeClock, FakeStageReporter, InMemoryStorage
from tests.fixtures.pipeline_fakes import (
    FakeEncoder,
    FakeLabels,
    FakeLipSync,
    FakeQuality,
    FakeVoice,
    PreviewEvents,
)
from vidgen.domain.codes import FailureCode
from vidgen.domain.outcomes import RowOutcomeKind
from vidgen.ports.rows import ClaimResult, RowJob, RowUpdate, TemplateInfo
from vidgen.services.render_row import RenderConfig, RowRenderer

BATCH = UUID("6f1c2a3e-8b7d-4e21-9c0a-1d2e3f4a5b6c")
ROW = UUID("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d")
TEMPLATE_KEY = "templates/t.mp4"
FOLDER = "2026-10-18-2"
PREVIEW_KEY = f"previews/{BATCH}.mp4"
CREATOR = "Test Creator Org"
PAUSE_S = 0.6
STAGES = ["fetch", "tts", "lipsync", "encode", "check", "publish"]
JOB = RowJob(
    batch_id=BATCH,
    row_id=ROW,
    row_number=2,
    name="Asha Verma",
    spoken_name=None,
    voter_id="A1",
    attempts=1,
    folder_name=FOLDER,
    template=TemplateInfo(
        video_key=TEMPLATE_KEY,
        width=320,
        height=240,
        slot=(1.0, 1.6),
        slot_confirmed=True,
        consent_confirmed=True,
    ),
)


class FakeRowStore:
    """RowStore double: hands out one job (or none) and remembers finished rows."""

    def __init__(self, job: RowJob | None) -> None:
        self.job = job
        self.finished: list[RowUpdate] = []

    def claim(self, batch_id: UUID, row_id: UUID, decide: Any, now: Any) -> ClaimResult:
        """The job to render, or NOOP when there is none."""
        if self.job is None:
            return ClaimResult(RowOutcomeKind.NOOP, None)
        return ClaimResult(RowOutcomeKind.COMPLETED, self.job)

    def preview_job(self, batch_id: UUID, row_id: UUID) -> RowJob | None:
        """The preview job, or None when the batch or row is gone."""
        return self.job

    def finish(
        self, batch_id: UUID, row_id: UUID, update: RowUpdate, now: Any, decide: Any
    ) -> None:
        """Remember the final state of the row."""
        self.finished.append(update)


class _Sink(PreviewEvents):
    """PreviewSink double that also writes into the shared log, to check the ordering."""

    def __init__(self, log: list[str]) -> None:
        super().__init__()
        self._log = log

    def preview_rendered(self, batch_id: object, key: str) -> None:
        """Record a finished preview in the log and in the events."""
        self._log.append("rendered")
        super().preview_rendered(batch_id, key)

    def preview_failed(self, batch_id: object, code: object) -> None:
        """Record a failed preview in the log and in the events."""
        self._log.append("failed")
        super().preview_failed(batch_id, code)


@dataclass
class Harness:
    """One renderer with every double it talks to."""

    renderer: RowRenderer
    storage: InMemoryStorage
    sink: _Sink
    stage: FakeStageReporter | None
    log: list[str]
    voice: FakeVoice
    quality: FakeQuality
    store: FakeRowStore


def build(*, reporter_on: bool = True, job: RowJob | None = JOB) -> Harness:
    """A renderer wired to fakes; ``reporter_on=False`` leaves stage_reporter out entirely."""
    log: list[str] = []
    storage = InMemoryStorage()
    storage.write(TEMPLATE_KEY, io.BytesIO(b"TEMPLATE-VIDEO"))
    store = FakeRowStore(job)
    sink = _Sink(log)
    voice, quality = FakeVoice(), FakeQuality()
    stage = FakeStageReporter(log) if reporter_on else None
    options: dict[str, Any] = {}
    if stage is not None:
        options["stage_reporter"] = stage
    renderer = RowRenderer(
        row_store_factory=lambda: store,
        storage=storage,
        voice=voice,
        lipsync=FakeLipSync(),
        encoder=FakeEncoder(),
        quality=quality,
        labels=FakeLabels(),
        clock=FakeClock(),
        config=RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S),
        preview_sink=sink,
        **options,
    )
    return Harness(renderer, storage, sink, stage, log, voice, quality, store)


def stage_entries(*names: str) -> list[str]:
    """The log entries a reporter writes for these stage names."""
    return [f"stage:{name}" for name in names]


# ---- positive ----------------------------------------------------------------------------


def test_preview_reports_each_stage_for_the_preview_batch_in_order() -> None:
    """P1/P2: fetch, tts, lipsync, encode, check, publish, all for the batch id (never the row)."""
    h = build()
    assert h.renderer.render_preview(BATCH, ROW).kind is RowOutcomeKind.COMPLETED
    assert h.stage is not None
    assert h.stage.reports == [(BATCH, name) for name in STAGES]
    assert all(batch == BATCH and name != str(ROW) for batch, name in h.stage.reports)


def test_success_reports_rendered_then_clears_the_stage() -> None:
    """P1: the stage is cleared after the preview is reported as rendered."""
    h = build()
    h.renderer.render_preview(BATCH, ROW)
    assert h.log == [*stage_entries(*STAGES), "rendered", "clear"]
    assert h.stage is not None and h.stage.cleared == [BATCH]


def test_preview_without_a_reporter_renders_exactly_as_before() -> None:
    """P3: no stage_reporter (the default) means no progress and no change in outcome."""
    h = build(reporter_on=False)
    outcome = h.renderer.render_preview(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert h.sink.rendered == [(BATCH, PREVIEW_KEY)]
    assert h.storage.files[PREVIEW_KEY] == b"ENC"


# ---- negative ----------------------------------------------------------------------------


def test_a_reporter_that_raises_on_report_does_not_fail_the_preview(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N1: the preview is still rendered and reported; the reporter error is logged."""
    caplog.set_level(logging.DEBUG)
    h = build()
    assert h.stage is not None
    h.stage.fail_report = RuntimeError("redis unavailable")
    outcome = h.renderer.render_preview(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert h.sink.rendered == [(BATCH, PREVIEW_KEY)]
    assert h.storage.files[PREVIEW_KEY] == b"ENC"
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_a_reporter_that_raises_on_clear_still_reports_the_preview() -> None:
    """N2: a failed clear after success is logged and does not change the result."""
    h = build()
    assert h.stage is not None
    h.stage.fail_clear = RuntimeError("redis unavailable")
    outcome = h.renderer.render_preview(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert h.sink.rendered == [(BATCH, PREVIEW_KEY)]


def test_a_raising_reporter_does_not_hide_the_failure_code() -> None:
    """N3: a failed preview with a broken reporter is still reported with its code."""
    h = build()
    assert h.stage is not None
    h.stage.fail_report = RuntimeError("redis unavailable")
    h.stage.fail_clear = RuntimeError("redis unavailable")
    h.voice.reported = 0.0  # zero-length speech: TTS_FAILED
    outcome = h.renderer.render_preview(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert h.sink.failed == [(BATCH, FailureCode.TTS_FAILED)]


@pytest.mark.parametrize(
    ("setup", "reached"),
    [
        pytest.param(lambda h: setattr(h.voice, "reported", 0.0), ["fetch", "tts"], id="tts"),
        pytest.param(
            lambda h: setattr(h.quality, "result", ["blur"]),
            ["fetch", "tts", "lipsync", "encode", "check"],
            id="check",
        ),
    ],
)
def test_failed_preview_reports_failed_then_clears_the_stage(
    setup: Any, reached: list[str]
) -> None:
    """N4: the stages up to the failure, then failed, then clear; nothing is published."""
    h = build()
    setup(h)
    outcome = h.renderer.render_preview(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert h.log == [*stage_entries(*reached), "failed", "clear"]
    assert h.stage is not None and h.stage.cleared == [BATCH]
    assert PREVIEW_KEY not in h.storage.files


# ---- edge --------------------------------------------------------------------------------


def test_a_preview_for_a_vanished_row_reports_nothing() -> None:
    """E1: no job means no stage runs, so nothing is reported or cleared."""
    h = build(job=None)
    outcome = h.renderer.render_preview(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.NOOP
    assert h.log == []
    assert h.stage is not None and h.stage.reports == [] and h.stage.cleared == []


def test_a_row_job_success_never_reports_progress() -> None:
    """E2: only previews report; a real row render leaves the reporter alone."""
    h = build()
    outcome = h.renderer.render(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert h.stage is not None
    assert h.stage.reports == [] and h.stage.cleared == []
    assert h.store.finished and h.store.finished[0].status == "COMPLETED"


def test_a_row_job_failure_never_reports_progress() -> None:
    """E2: a failed row render does not report either."""
    h = build()
    h.voice.reported = 0.0
    outcome = h.renderer.render(BATCH, ROW)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert h.log == []
