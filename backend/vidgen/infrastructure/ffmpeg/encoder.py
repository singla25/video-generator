"""FFmpeg video engine: splices the new name audio, overlays the label, writes metadata.

The engine executes a ``TimingPlan`` computed by the domain; it never recomputes timing.
Speech is sped up with ``atempo`` (this ffmpeg build may lack ``rubberband``; atempo is
the portable choice). Output is written to a temporary file next to the target and
published with a hard link, so an existing file is never overwritten and a failure leaves
nothing behind.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from vidgen.domain.timing import TimingPlan, TimingRules
from vidgen.infrastructure.ffmpeg import graph, loudness
from vidgen.infrastructure.ffmpeg.facts import TemplateFacts, read_template_facts
from vidgen.infrastructure.ffmpeg.runner import run_tool

DEFAULT_FFPROBE = "ffprobe"
DEFAULT_TIMEOUT_S = 600.0
DEFAULT_MAX_STRETCH_RATIO = 0.15
OUTPUT_FORMAT = "mp4"
PART_SUFFIX = ".part"
_MEASURE_FLAGS = ["-hide_banner", "-nostats", "-nostdin"]


class FfmpegVideoEncoder:
    """Renders one output video from a template and a new name recording."""

    def __init__(
        self,
        ffmpeg_path: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_S,
        crossfade_ms: int = TimingRules().crossfade_ms,
        *,
        ffprobe_path: str | None = None,
        max_stretch_ratio: float = DEFAULT_MAX_STRETCH_RATIO,
    ) -> None:
        self._ffmpeg = ffmpeg_path
        self._ffprobe = ffprobe_path or _sibling_ffprobe(ffmpeg_path)
        self._timeout = timeout_seconds
        self._crossfade_s = TimingRules(crossfade_ms=crossfade_ms).crossfade_s  # validates 20-50
        self._max_stretch = max_stretch_ratio

    def render(
        self,
        template: Path,
        new_slot_audio: Path,
        slot: tuple[float, float],
        plan: TimingPlan,
        label_png: Path,
        metadata: Mapping[str, str],
        out: Path,
    ) -> None:
        """Write the finished video to ``out`` (which must not exist)."""
        meta = dict(metadata)
        self._check_stretch(plan)
        graph.validate_metadata(meta)
        if out.exists():
            raise FileExistsError(out.name)
        facts = read_template_facts(self._ffprobe, template, self._timeout)
        gain = self._gain_db(template, new_slot_audio, slot, plan, facts)
        command = self._command(template, new_slot_audio, slot, plan, label_png, meta, facts, gain)
        with _temp_output(out) as temp:
            run_tool([*command, str(temp)], self._timeout)
            os.link(temp, out)  # raises FileExistsError instead of overwriting

    def _check_stretch(self, plan: TimingPlan) -> None:
        """Refuse a plan that stretches speech by more than the allowed ratio (R3.5)."""
        if abs(plan.stretch_factor - 1.0) > self._max_stretch + graph.EPSILON_S:
            raise ValueError("plan stretch is beyond the allowed ratio")

    def _gain_db(
        self,
        template: Path,
        audio: Path,
        slot: tuple[float, float],
        plan: TimingPlan,
        facts: TemplateFacts,
    ) -> float:
        """Gain that matches the new name's loudness to the template slot's."""
        start, end = slot
        template_lufs = self._measure(
            ["-ss", graph.seconds(start), "-t", graph.seconds(end - start), "-i", str(template)],
            "anull",
        )
        new_lufs = self._measure(["-i", str(audio)], graph.stretch_chain(facts, plan))
        return loudness.gain_db(template_lufs, new_lufs)

    def _measure(self, input_args: list[str], prefilter: str) -> float | None:
        """Integrated loudness of an input after ``prefilter``."""
        command = [
            self._ffmpeg, *_MEASURE_FLAGS, *input_args, "-vn",
            "-af", f"{prefilter},ebur128", "-f", "null", os.devnull,
        ]  # fmt: skip
        return loudness.parse_integrated_lufs(run_tool(command, self._timeout).stderr)

    def _command(
        self,
        template: Path,
        audio: Path,
        slot: tuple[float, float],
        plan: TimingPlan,
        label: Path,
        metadata: dict[str, str],
        facts: TemplateFacts,
        gain_db: float,
    ) -> list[str]:
        """The render command without the output path."""
        filters = ";".join(
            [
                graph.video_graph(facts, slot, plan),
                graph.audio_graph(facts, slot, plan, self._crossfade_s, gain_db),
            ]
        )
        return [
            self._ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y",
            "-i", str(template), "-i", str(audio), "-i", str(label),
            "-filter_complex", filters, "-map", "[vout]", "-map", "[aout]",
            *graph.codec_args(facts), "-pix_fmt", facts.pix_fmt,
            "-c:a", graph.AUDIO_CODEC, "-b:a", graph.AUDIO_BITRATE,
            "-map_metadata", "-1", "-map_chapters", "-1", *graph.metadata_args(metadata),
            "-movflags", "+faststart+use_metadata_tags", "-f", OUTPUT_FORMAT,
        ]  # fmt: skip


def _sibling_ffprobe(ffmpeg_path: str) -> str:
    """ffprobe next to ffmpeg if present, else the one on PATH."""
    sibling = Path(ffmpeg_path).with_name(DEFAULT_FFPROBE)
    return str(sibling) if sibling.is_file() else DEFAULT_FFPROBE


@contextlib.contextmanager
def _temp_output(out: Path) -> Iterator[Path]:
    """A temporary file beside ``out``; removed on exit whatever happens."""
    fd, name = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=PART_SUFFIX)
    os.close(fd)
    temp = Path(name)
    try:
        yield temp
    finally:
        temp.unlink(missing_ok=True)


if TYPE_CHECKING:  # pragma: no cover
    from vidgen.ports import VideoEncoder

    def _satisfies_port(adapter: FfmpegVideoEncoder) -> VideoEncoder:
        return adapter
