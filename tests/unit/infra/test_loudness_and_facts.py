"""Loudness helpers (B10) and template-fact parsing (AC8) as pure functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.ffmpeg.facts import TemplateFacts, parse_facts, read_template_facts
from vidgen.infrastructure.ffmpeg.loudness import gain_db, parse_integrated_lufs

SUMMARY = """
  Integrated loudness:
    I:         -23.4 LUFS
    Threshold: -33.5 LUFS
"""

GOOD = {
    "format": {"duration": "4.000000"},
    "streams": [
        {
            "codec_type": "video",
            "r_frame_rate": "30000/1001",
            "codec_name": "h264",
            "pix_fmt": "yuv420p",
        },
        {"codec_type": "audio", "sample_rate": "48000", "channel_layout": "stereo"},
    ],
}


# ---- loudness -------------------------------------------------------------------------


def test_integrated_loudness_is_read_from_the_last_summary_line() -> None:
    """TT-AC9-P9."""
    text = "I:  -40.0 LUFS\n" + SUMMARY
    assert parse_integrated_lufs(text) == pytest.approx(-23.4)


def test_output_without_a_loudness_figure_is_unmeasurable() -> None:
    """TT-AC9-E8."""
    assert parse_integrated_lufs("no figures here") is None
    assert parse_integrated_lufs("") is None


@pytest.mark.parametrize("value", ["-70.0", "-120.7"])
def test_silence_floor_values_are_unmeasurable(value: str) -> None:
    """TT-AC9-E8: ebur128 reports about -70 LUFS for silence."""
    assert parse_integrated_lufs(f"I:  {value} LUFS") is None


def test_gain_brings_the_new_audio_to_the_template_level() -> None:
    """TT-AC9-P9."""
    assert gain_db(-20.0, -26.0) == pytest.approx(6.0)
    assert gain_db(-20.0, -14.0) == pytest.approx(-6.0)


@pytest.mark.parametrize(("template", "new"), [(None, -20.0), (-20.0, None), (None, None)])
def test_gain_is_zero_when_a_level_is_unmeasurable(
    template: float | None, new: float | None
) -> None:
    """TT-AC9-E8."""
    assert gain_db(template, new) == 0.0


def test_gain_is_limited_to_24_db_either_way() -> None:
    """TT-AC9-E8: a huge correction signals bad input and is capped."""
    assert gain_db(-10.0, -60.0) == 24.0
    assert gain_db(-60.0, -10.0) == -24.0


# ---- facts ----------------------------------------------------------------------------


def test_facts_are_read_from_probe_json() -> None:
    """TT-AC8-P1."""
    assert parse_facts(GOOD) == TemplateFacts(4.0, "30000/1001", "h264", "yuv420p", 48000, "stereo")


@pytest.mark.parametrize("missing", ["video", "audio"])
def test_template_without_a_video_or_audio_stream_is_an_internal_error(missing: str) -> None:
    """TT-AC1-E4."""
    data = {
        "format": GOOD["format"],
        "streams": [s for s in GOOD["streams"] if s["codec_type"] != missing],  # type: ignore[index, union-attr]
    }
    with pytest.raises(DomainError) as info:
        parse_facts(data)
    assert info.value.code is FailureCode.INTERNAL_ERROR


def test_probe_json_with_missing_fields_is_an_internal_error() -> None:
    """TT-AC1-N5."""
    broken = {"format": {}, "streams": GOOD["streams"]}
    with pytest.raises(DomainError) as info:
        parse_facts(broken)
    assert info.value.code is FailureCode.INTERNAL_ERROR


def test_probe_json_with_non_numeric_values_is_an_internal_error() -> None:
    """TT-AC1-N5."""
    broken = {
        "format": {"duration": "N/A"},
        "streams": GOOD["streams"],
    }
    with pytest.raises(DomainError) as info:
        parse_facts(broken)
    assert info.value.code is FailureCode.INTERNAL_ERROR


def test_unparsable_ffprobe_output_is_an_internal_error(tmp_path: Path) -> None:
    """TT-AC1-N5: a tool that prints garbage instead of JSON."""
    fake = tmp_path / "fake_ffprobe"
    fake.write_text("#!/bin/sh\necho 'not json'\n", encoding="utf-8")
    fake.chmod(0o755)
    with pytest.raises(DomainError) as info:
        read_template_facts(str(fake), tmp_path / "t.mp4", 5.0)
    assert info.value.code is FailureCode.INTERNAL_ERROR
