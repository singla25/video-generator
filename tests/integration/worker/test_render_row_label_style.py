"""The row pipeline picks the label size by style: bubble = full frame, band = strip (DD-32)."""

from __future__ import annotations

import pytest

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import CREATOR, PAUSE_S, World
from vidgen.domain.codes import FailureCode
from vidgen.infrastructure.fakes.adapters import FakeQualityChecker
from vidgen.services.render_row import RenderConfig, RowOutcomeKind


def config(**kwargs: object) -> RenderConfig:
    """A render config for the tests."""
    return RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S, **kwargs)  # type: ignore[arg-type]


def render(world: World):  # type: ignore[no-untyped-def]
    """Render the world's single row."""
    return world.renderer.render(world.batch_id, world.rows[2])


def test_default_style_asks_for_a_label_the_size_of_the_template_frame(world: World) -> None:
    """LS-P-P1: bubble is the default; the label adds no height."""
    assert RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S).label_style == "bubble"
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.labels.sizes == [(320, 240)]


def test_band_style_asks_for_the_ten_percent_strip(make_world: WorldFactory) -> None:
    """LS-P-P2: unchanged band behaviour when asked for explicitly."""
    world = make_world(config=config(label_style="band"))
    render(world)
    assert world.labels.sizes == [(320, 24)]


def test_band_height_is_not_applied_for_bubble(
    make_world: WorldFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LS-P-P4."""

    def boom(*args: object, **kwargs: object) -> int:
        raise AssertionError("band_height must not be used for the bubble")

    monkeypatch.setattr("vidgen.services.render_row.band_height", boom)
    world = make_world(config=config(label_style="bubble"))
    assert render(world).kind is RowOutcomeKind.COMPLETED


def test_band_share_is_ignored_for_bubble_and_honoured_for_band(
    make_world: WorldFactory,
) -> None:
    """LS-P-E1."""
    bubble = make_world(config=config(label_style="bubble", label_band_share=0.2))
    render(bubble)
    assert bubble.labels.sizes == [(320, 240)]
    band = make_world(config=config(label_style="band", label_band_share=0.2))
    render(band)
    assert band.labels.sizes == [(320, 48)]


def test_bubble_row_runs_the_quality_check_and_completes(world: World) -> None:
    """LS-P-P5, LS-Q-P1: no band is expected by the checks."""
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.order == ["tts", "lipsync", "encode", "check"]
    assert world.quality.count == 1
    assert world.row(2)["status"] == "COMPLETED"


def test_a_failing_quality_check_still_fails_a_bubble_row(world: World) -> None:
    """LS-Q-E1: the bubble does not weaken the output check."""
    world.quality.result = ["blurry"]
    outcome = render(world)
    assert outcome.code is FailureCode.OUTPUT_CHECK_FAILED


def test_the_fake_quality_checker_accepts_a_bubble_output(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """LS-Q-P1: nothing in the checker looks for a band."""
    video = tmp_path / "out.mp4"
    video.write_bytes(b"x")
    assert FakeQualityChecker().check(video, video) == []


def test_an_unknown_style_is_rejected_by_the_render_config() -> None:
    """LS-P-N1: no silent fallback to a band or a bubble."""
    with pytest.raises(ValueError, match="label_style"):
        config(label_style="stripe")
