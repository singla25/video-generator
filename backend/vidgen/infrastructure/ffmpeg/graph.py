"""Pure builders for the FFmpeg filter graph and output options.

Everything here maps a ``TimingPlan`` and the template facts to strings. Nothing runs ffmpeg,
so it can be tested exhaustively. The engine only executes the plan; it never recomputes it.

Audio layout (template time ``t``; slot = [start, end]):
  head   = template[0, start + cf]            kept as is
  region = new name, stretched, padded         replaces [start, end + absorbed + extension]
  tail   = template[end + absorbed - cf, T]    keeps its place, shifted by the extension
Head/region and region/tail are joined with a crossfade of ``cf`` seconds.
"""

from __future__ import annotations

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.timing import TimingPlan
from vidgen.infrastructure.ffmpeg.facts import TemplateFacts

EPSILON_S = 1e-6
H264 = "h264"
HEVC = "hevc"
VIDEO_PRESET = "veryfast"
VIDEO_CRF = "18"
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "128k"
CROSSFADE_CURVE = "qsin"  # equal-power fade: no dip in level at the joint
LABEL_INPUT = "2:v"
REQUIRED_METADATA = ("creator_entity", "generated_on", "batch_id")
MAX_METADATA_CHARS = 1024


def seconds(value: float) -> str:
    """Format seconds for a filter argument."""
    return f"{value:.6f}"


def region_length(slot: tuple[float, float], plan: TimingPlan) -> float:
    """Output length of the part that replaces the slot (slot + absorbed pause + extension)."""
    return slot[1] - slot[0] + plan.pause_absorbed_s + plan.extension_s


def tail_start(slot: tuple[float, float], plan: TimingPlan) -> float:
    """Template time where untouched audio resumes."""
    return slot[1] + plan.pause_absorbed_s


def audio_format(facts: TemplateFacts) -> str:
    """Filter that converts any audio to the template's rate and channel layout."""
    return (
        f"aformat=sample_fmts=fltp:sample_rates={facts.sample_rate}"
        f":channel_layouts={facts.channel_layout}"
    )


def stretch_chain(facts: TemplateFacts, plan: TimingPlan) -> str:
    """Convert the new audio to the template format and apply the planned speed-up."""
    chain = audio_format(facts)
    if abs(plan.stretch_factor - 1.0) > EPSILON_S:
        chain += f",atempo={1.0 / plan.stretch_factor:.6f}"
    return chain


def region_chain(
    facts: TemplateFacts, slot: tuple[float, float], plan: TimingPlan, gain_db: float
) -> str:
    """Full filter chain that turns the new recording into the region audio."""
    length = seconds(region_length(slot, plan))
    return (
        f"{stretch_chain(facts, plan)},volume={gain_db:.3f}dB,"
        f"apad=whole_dur={length},atrim=end={length},asetpts=PTS-STARTPTS"
    )


def audio_graph(
    facts: TemplateFacts,
    slot: tuple[float, float],
    plan: TimingPlan,
    crossfade_s: float,
    gain_db: float,
) -> str:
    """Filter graph producing ``[aout]``: head + crossfade + region + crossfade + tail."""
    start, _ = slot
    resume = min(tail_start(slot, plan), facts.duration_s)
    parts = [f"[1:a]{region_chain(facts, slot, plan, gain_db)}[mid]"]
    current = "mid"
    fade = f"acrossfade=d={seconds(crossfade_s)}:c1={CROSSFADE_CURVE}:c2={CROSSFADE_CURVE}"
    if start > EPSILON_S:
        head_end = seconds(start + crossfade_s)
        parts.append(f"[0:a]{audio_format(facts)},atrim=end={head_end},asetpts=PTS-STARTPTS[head]")
        parts.append(f"[head][{current}]{fade}[joined]")
        current = "joined"
    if resume < facts.duration_s - EPSILON_S:
        tail_from = seconds(resume - crossfade_s)
        parts.append(
            f"[0:a]{audio_format(facts)},atrim=start={tail_from},asetpts=PTS-STARTPTS[tail]"
        )
        parts.append(f"[{current}][tail]{fade}[final]")
        current = "final"
    parts.append(f"[{current}]anull[aout]")
    return ";".join(parts)


def _video_segments(
    facts: TemplateFacts, slot: tuple[float, float], extension_s: float
) -> list[str]:
    """Trim expressions for the template video, with the slot slowed by the extension (D-11)."""
    start, end = slot
    slow = (end - start + extension_s) / (end - start)
    segments: list[str] = []
    if start > EPSILON_S:
        segments.append(f"trim=end={seconds(start)},setpts=PTS-STARTPTS")
    segments.append(
        f"trim=start={seconds(start)}:end={seconds(end)},setpts=(PTS-STARTPTS)*{slow:.6f}"
    )
    if end < facts.duration_s - EPSILON_S:
        segments.append(f"trim=start={seconds(end)},setpts=PTS-STARTPTS")
    return segments


def video_graph(facts: TemplateFacts, slot: tuple[float, float], plan: TimingPlan) -> str:
    """Filter graph producing ``[vout]``: optional slow-down, constant fps, label overlay."""
    if plan.extension_s > EPSILON_S:
        segments = _video_segments(facts, slot, plan.extension_s)
        names = [f"[s{i}]" for i in range(len(segments))]
        split = f"[0:v]split={len(segments)}" + "".join(f"[i{i}]" for i in range(len(segments)))
        trims = [f"[i{i}]{seg}{names[i]}" for i, seg in enumerate(segments)]
        join = f"{''.join(names)}concat=n={len(segments)}:v=1:a=0,fps={facts.fps}[base]"
        base = ";".join([split, *trims, join])
    else:
        base = f"[0:v]fps={facts.fps}[base]"
    overlay = f"[base][{LABEL_INPUT}]overlay=0:0:format=auto,format={facts.pix_fmt}[vout]"
    return f"{base};{overlay}"


def codec_args(facts: TemplateFacts) -> list[str]:
    """Video encoder options that keep the template's codec family."""
    if facts.video_codec == H264:
        return ["-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", VIDEO_CRF]
    if facts.video_codec == HEVC:
        return ["-c:v", "libx265", "-preset", VIDEO_PRESET, "-crf", VIDEO_CRF,
                "-tag:v", "hvc1", "-x265-params", "log-level=error"]  # fmt: skip
    raise DomainError(FailureCode.UNSUPPORTED_VIDEO)


def metadata_args(metadata: dict[str, str]) -> list[str]:
    """``-metadata`` options for our keys only; template tags are dropped by the caller."""
    args: list[str] = []
    for key, value in metadata.items():
        args += ["-metadata", f"{key}={value[:MAX_METADATA_CHARS]}"]
    return args


def validate_metadata(metadata: dict[str, str]) -> None:
    """The creator entity, date and batch id are mandatory and non-blank (C3)."""
    for key in REQUIRED_METADATA:
        if not metadata.get(key, "").strip():
            raise ValueError(f"metadata '{key}' is required")
