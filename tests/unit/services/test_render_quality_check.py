"""BL-14: the check stage passes the expected output and fails without leaking the name."""

from __future__ import annotations

import dataclasses
import io
import logging
from dataclasses import dataclass

import pytest

from tests.fixtures.doubles import FakeClock, InMemoryStorage
from tests.fixtures.names import DEVANAGARI_NAME
from tests.fixtures.pipeline_fakes import (
    FakeEncoder,
    FakeLabels,
    FakeLipSync,
    FakeQuality,
    FakeVoice,
    PreviewEvents,
)
from tests.unit.services.test_render_preview_stage import (
    BATCH,
    CREATOR,
    JOB,
    PAUSE_S,
    ROW,
    TEMPLATE_KEY,
    FakeRowStore,
)
from vidgen.domain.codes import FailureCode
from vidgen.domain.quality import QualityIssue
from vidgen.domain.timing import expected_output
from vidgen.ports.rows import RowJob
from vidgen.services.render_row import RenderConfig, RowRenderer

LATIN = "Krishan"


def named(name: str) -> RowJob:
    """The preview job, for a person called ``name``."""
    return dataclasses.replace(JOB, name=name)


@dataclass
class Harness:
    """A renderer wired to fakes, keeping the ones the tests look into."""

    renderer: RowRenderer
    sink: PreviewEvents
    quality: FakeQuality
    encoder: FakeEncoder


def build(*, job: RowJob = JOB) -> Harness:
    """A preview renderer over in-memory fakes."""
    storage = InMemoryStorage()
    storage.write(TEMPLATE_KEY, io.BytesIO(b"TEMPLATE-VIDEO"))
    sink, quality, encoder = PreviewEvents(), FakeQuality(), FakeEncoder()
    renderer = RowRenderer(
        row_store_factory=lambda: FakeRowStore(job),
        storage=storage,
        voice=FakeVoice(),
        lipsync=FakeLipSync(),
        encoder=encoder,
        quality=quality,
        labels=FakeLabels(),
        clock=FakeClock(),
        config=RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S),
        preview_sink=sink,
    )
    return Harness(renderer, sink, quality, encoder)


def render(h: Harness) -> None:
    """Run the preview (it goes through the same fetch..check stages as a row)."""
    h.renderer.render_preview(BATCH, ROW)


# ---- positive ----------------------------------------------------------------------------


def test_check_receives_an_expectation_built_from_the_slots_and_plans() -> None:
    h = build()
    render(h)
    assert h.quality.count == 1
    (expected,) = h.quality.expectations
    assert expected is not None
    assert len(expected.regions) == len(JOB.template.slots)
    assert expected.regions[0].template[0] == pytest.approx(JOB.template.slots[0][0])
    # Same numbers the pure function gives for the plans the encoder was handed.
    plans = [call.plan for call in h.encoder.calls]
    assert expected == expected_output(JOB.template.slots, plans)
    assert expected.delta_s == pytest.approx(sum(p.duration_delta_s for p in plans))


# ---- negative ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "issues",
    [
        [QualityIssue.DURATION_MISMATCH],
        [QualityIssue.LOUDNESS_MISMATCH, QualityIssue.AUDIO_SILENT],
        ["UNREADABLE_OUTPUT"],
    ],
)
def test_any_reported_issue_fails_the_preview_with_output_check_failed(issues: list[str]) -> None:
    h = build()
    h.quality.result = list(issues)
    render(h)
    assert h.sink.failed == [(BATCH, FailureCode.OUTPUT_CHECK_FAILED)]
    assert h.sink.rendered == []


@pytest.mark.parametrize("name", [LATIN, DEVANAGARI_NAME])
def test_failure_logs_and_code_never_contain_the_name(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    h = build(job=named(name))
    h.quality.result = [QualityIssue.DURATION_MISMATCH]
    render(h)
    assert h.sink.failed == [(BATCH, FailureCode.OUTPUT_CHECK_FAILED)]
    assert name not in caplog.text
    assert all(name not in str(record.__dict__) for record in caplog.records)
    assert name not in str(h.sink.failed)


# ---- edge --------------------------------------------------------------------------------


def test_success_still_logs_no_name(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    h = build(job=named(LATIN))
    render(h)
    assert h.sink.rendered
    assert LATIN not in caplog.text
