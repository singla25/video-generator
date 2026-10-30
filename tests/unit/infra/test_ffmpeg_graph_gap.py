"""Filter graph for the name gap (DD-34): the slot region and its video hold grow by gap_s.

Pure string checks, like test_ffmpeg_graph.py. Only the slot changes; the tail keeps its place.
"""

from __future__ import annotations

import pytest

from vidgen.domain.timing import TimingPlan
from vidgen.infrastructure.ffmpeg.facts import TemplateFacts
from vidgen.infrastructure.ffmpeg.graph import (
    audio_graph,
    region_length,
    tail_start,
    video_graph,
)

SLOT = (1.0, 2.0)
GAP = 0.25
HOLD = "tpad=stop_mode=clone:stop_duration=0.250000"


def facts() -> TemplateFacts:
    """Template facts for a 4 s clip, 25 fps, 16 kHz mono audio."""
    return TemplateFacts(4.0, "25/1", "h264", "yuv420p", 16000, "mono")


def plain_gap() -> TimingPlan:
    """Slot 1.0 s, nothing absorbed or extended, name fits; 0.25 s gap after it."""
    return TimingPlan(1.0, 0.0, 0.0, 0.0, 1.25, gap_s=GAP)


def extended_gap() -> TimingPlan:
    """Slot 1.0 s, 0.6 s pause absorbed, 0.5 s extension, 0.25 s gap."""
    return TimingPlan(0.85, 0.6, 0.5, 0.0, 2.35, gap_s=GAP)


def plain_no_gap() -> TimingPlan:
    """Same as plain_gap with gap 0: the graph must be what it was before the feature."""
    return TimingPlan(1.0, 0.0, 0.0, 0.0, 1.0, gap_s=0.0)


# ---- region and tail ------------------------------------------------------------------


def test_region_length_includes_the_gap() -> None:
    """DD-34: slot + absorbed pause + extension + gap (1.0 + 0.6 + 0.5 + 0.25 = 2.35 s)."""
    assert region_length(SLOT, plain_gap()) == pytest.approx(1.25)
    assert region_length(SLOT, extended_gap()) == pytest.approx(2.35)


def test_region_length_with_zero_gap_is_unchanged() -> None:
    """DD-34 default: gap 0 keeps the region at slot + absorbed + extension."""
    assert region_length(SLOT, plain_no_gap()) == pytest.approx(1.0)


def test_tail_start_does_not_move_for_the_gap() -> None:
    """DD-34: the untouched tail still resumes at slot end + absorbed pause (2.6 s here)."""
    assert tail_start(SLOT, extended_gap()) == pytest.approx(2.6)
    assert tail_start(SLOT, plain_gap()) == pytest.approx(2.0)


# ---- audio graph ----------------------------------------------------------------------


def test_audio_region_is_padded_and_trimmed_to_the_longer_length() -> None:
    """DD-34: the region chain uses the gap-extended length in apad and atrim."""
    graph = audio_graph(facts(), SLOT, plain_gap(), 0.03, 0.0)
    assert "apad=whole_dur=1.250000" in graph
    assert "atrim=end=1.250000" in graph


def test_audio_region_with_extension_and_gap_uses_the_full_length() -> None:
    """DD-34: slot + absorbed + extension + gap = 2.35 s."""
    graph = audio_graph(facts(), SLOT, extended_gap(), 0.03, 0.0)
    assert "apad=whole_dur=2.350000" in graph
    assert "atrim=end=2.350000" in graph


def test_audio_tail_still_starts_at_the_unchanged_tail_point() -> None:
    """DD-34: the tail is cut from template 2.6 s minus the crossfade, as without the gap."""
    graph = audio_graph(facts(), SLOT, extended_gap(), 0.03, 0.0)
    assert "atrim=start=2.570000" in graph


# ---- video graph ----------------------------------------------------------------------


def test_video_graph_with_gap_holds_the_last_slot_frame() -> None:
    """DD-34: the slot segment gets tpad clone after its setpts, at slow factor 1.000000."""
    graph = video_graph(facts(), SLOT, plain_gap())
    assert HOLD in graph
    assert (
        "trim=start=1.000000:end=2.000000,setpts=(PTS-STARTPTS)*1.000000,"
        "tpad=stop_mode=clone:stop_duration=0.250000"
    ) in graph


def test_video_graph_with_gap_uses_the_split_and_concat_branch() -> None:
    """DD-34: a gap without extension still goes through split + concat (slot in the middle)."""
    graph = video_graph(facts(), SLOT, plain_gap())
    assert "split=3" in graph
    assert "concat=n=3" in graph


def test_video_graph_with_gap_and_extension_has_slow_down_and_hold_in_the_slot() -> None:
    """DD-34: the slot segment carries both the 1.5x slow-down and the hold, in that order."""
    graph = video_graph(facts(), SLOT, extended_gap())
    assert (
        "trim=start=1.000000:end=2.000000,setpts=(PTS-STARTPTS)*1.500000,"
        "tpad=stop_mode=clone:stop_duration=0.250000"
    ) in graph
    assert graph.count("tpad") == 1


def test_video_graph_without_gap_has_no_hold() -> None:
    """DD-34 default: no tpad when the gap is zero."""
    assert "tpad" not in video_graph(facts(), SLOT, plain_no_gap())


def test_video_graph_with_zero_gap_and_no_extension_is_exactly_todays_graph() -> None:
    """DD-34 default: gap 0 and extension 0 give the same string as before the feature."""
    assert video_graph(facts(), SLOT, plain_no_gap()) == (
        "[0:v]fps=25/1[base];[base][2:v]overlay=0:0:format=auto,format=yuv420p[vout]"
    )
