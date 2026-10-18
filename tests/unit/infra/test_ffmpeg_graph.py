"""Pure filter-graph and option builders for the engine (AC8-AC10, D-10, D-11).

These functions only build strings from a TimingPlan and template facts, so every branch is
tested here without running ffmpeg.
"""

from __future__ import annotations

import pytest

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.timing import TimingPlan
from vidgen.infrastructure.ffmpeg.facts import TemplateFacts
from vidgen.infrastructure.ffmpeg.graph import (
    audio_graph,
    codec_args,
    metadata_args,
    validate_metadata,
    video_graph,
)

PLAIN = TimingPlan(1.0, 0.0, 0.0, 0.0, 1.0)
STRETCHED = TimingPlan(0.85, 0.0, 0.0, 0.0, 1.0)
EXTENDED = TimingPlan(0.85, 0.6, 0.5, 0.0, 2.1)


def facts(codec: str = "h264", duration: float = 4.0, fps: str = "25/1") -> TemplateFacts:
    """Template facts for a 4 s clip with 16 kHz mono audio."""
    return TemplateFacts(duration, fps, codec, "yuv420p", 16000, "mono")


# ---- audio graph ----------------------------------------------------------------------


def test_audio_graph_has_head_and_tail_when_slot_is_in_the_middle() -> None:
    """TT-AC9-P7: both template parts are kept and crossfaded."""
    graph = audio_graph(facts(), (1.0, 2.0), PLAIN, 0.03, 0.0)
    assert "[head]" in graph
    assert "[tail]" in graph
    assert graph.count("acrossfade") == 2
    assert graph.endswith("[aout]")


def test_audio_graph_has_no_head_when_slot_starts_at_zero() -> None:
    """TT-AC9-E5."""
    graph = audio_graph(facts(), (0.0, 1.0), PLAIN, 0.03, 0.0)
    assert "[head]" not in graph
    assert "[tail]" in graph
    assert graph.count("acrossfade") == 1


def test_audio_graph_has_no_tail_when_the_slot_runs_to_the_end() -> None:
    """TT-AC9-E5."""
    graph = audio_graph(facts(), (3.0, 4.0), PLAIN, 0.03, 0.0)
    assert "[tail]" not in graph
    assert "[head]" in graph
    assert graph.count("acrossfade") == 1


def test_audio_graph_for_a_slot_covering_everything_has_neither() -> None:
    """TT-AC9-E5."""
    graph = audio_graph(facts(), (0.0, 4.0), PLAIN, 0.03, 0.0)
    assert "acrossfade" not in graph
    assert "[aout]" in graph


def test_stretch_only_appears_for_a_stretched_plan() -> None:
    """TT-AC9-P2: speed = 1 / stretch_factor, only when the plan stretches."""
    assert "atempo" not in audio_graph(facts(), (1.0, 2.0), PLAIN, 0.03, 0.0)
    stretched = audio_graph(facts(), (1.0, 2.0), STRETCHED, 0.03, 0.0)
    assert "atempo=1.176471" in stretched


def test_gain_is_applied_to_the_new_audio() -> None:
    """TT-AC9-P9."""
    assert "volume=-6.500dB" in audio_graph(facts(), (1.0, 2.0), PLAIN, 0.03, -6.5)


def test_region_covers_slot_plus_absorbed_pause_plus_extension() -> None:
    """TT-AC9-P4: the replaced region is 1.0 + 0.6 + 0.5 = 2.1 s."""
    assert "apad=whole_dur=2.100000" in audio_graph(facts(), (1.0, 2.0), EXTENDED, 0.03, 0.0)


# ---- video graph ----------------------------------------------------------------------


def test_video_graph_without_extension_only_keeps_fps_and_overlays_the_label() -> None:
    """TT-AC8-P1, TT-AC10-P1."""
    graph = video_graph(facts(), (1.0, 2.0), PLAIN)
    assert "concat" not in graph
    assert "fps=25/1" in graph
    assert "overlay=0:0" in graph
    assert graph.endswith("[vout]")


def test_video_graph_with_extension_slows_the_slot_frames() -> None:
    """TT-AC9-P4, D-11: slot 1 s -> 1.5 s means a 1.5x slow-down, three segments joined."""
    graph = video_graph(facts(), (1.0, 2.0), TimingPlan(0.85, 0.6, 0.5, 0.0, 2.1))
    assert "concat=n=3" in graph
    assert "*1.500000" in graph


def test_video_graph_slot_at_start_has_no_leading_segment() -> None:
    """TT-AC9-E5."""
    graph = video_graph(facts(), (0.0, 1.0), TimingPlan(0.85, 0.0, 0.5, 0.0, 1.5))
    assert "concat=n=2" in graph


def test_video_graph_slot_at_end_has_no_trailing_segment() -> None:
    """TT-AC9-E5."""
    graph = video_graph(facts(), (3.0, 4.0), TimingPlan(0.85, 0.0, 0.5, 0.0, 1.5))
    assert "concat=n=2" in graph


def test_video_graph_slot_covering_the_whole_clip_is_a_single_segment() -> None:
    """TT-AC9-E5."""
    graph = video_graph(facts(), (0.0, 4.0), TimingPlan(0.85, 0.0, 0.5, 0.0, 1.5))
    assert "concat=n=1" in graph


def test_video_graph_keeps_the_template_pixel_format() -> None:
    """TT-AC8-P1."""
    assert "format=yuv420p[vout]" in video_graph(facts(), (1.0, 2.0), PLAIN)


# ---- codec and metadata ---------------------------------------------------------------


def test_h264_template_uses_the_h264_encoder() -> None:
    """TT-AC8-P1."""
    assert "libx264" in codec_args(facts("h264"))


def test_hevc_template_uses_the_hevc_encoder_with_hvc1_tag() -> None:
    """TT-AC8-P2."""
    args = codec_args(facts("hevc"))
    assert "libx265" in args
    assert "hvc1" in args


@pytest.mark.parametrize("codec", ["mpeg4", "vp9", "prores"])
def test_other_codecs_are_refused(codec: str) -> None:
    """TT-AC1-N2: the engine never silently changes the codec family."""
    with pytest.raises(DomainError) as info:
        codec_args(facts(codec))
    assert info.value.code is FailureCode.UNSUPPORTED_VIDEO


def test_metadata_args_are_key_value_pairs_and_long_values_are_cut() -> None:
    """TT-AC10-P4, E5."""
    args = metadata_args({"batch_id": "b1", "creator_entity": "x" * 5000})
    assert args[:2] == ["-metadata", "batch_id=b1"]
    assert len(args[3]) < 1100


def test_validate_metadata_accepts_complete_values() -> None:
    """TT-AC10-P4."""
    validate_metadata({"creator_entity": "Org", "generated_on": "2026-10-18", "batch_id": "b"})


@pytest.mark.parametrize("key", ["creator_entity", "generated_on", "batch_id"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_validate_metadata_rejects_missing_or_blank_required_values(
    key: str, value: str | None
) -> None:
    """TT-AC10-N1 (C3)."""
    metadata = {"creator_entity": "Org", "generated_on": "2026-10-18", "batch_id": "b"}
    if value is None:
        del metadata[key]
    else:
        metadata[key] = value
    with pytest.raises(ValueError, match=key):
        validate_metadata(metadata)
