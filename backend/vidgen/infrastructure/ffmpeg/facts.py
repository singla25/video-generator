"""Facts about the template video that the render graph needs, read with ffprobe."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.ffmpeg.runner import run_tool


@dataclass(frozen=True)
class TemplateFacts:
    """Format of the template that the output must keep (AC8, B10)."""

    duration_s: float
    fps: str  # exact ffprobe fraction such as "30000/1001"
    video_codec: str
    pix_fmt: str
    sample_rate: int
    channel_layout: str


def parse_facts(data: dict[str, Any]) -> TemplateFacts:
    """Build TemplateFacts from ffprobe JSON; missing streams are an internal error."""
    streams: list[dict[str, Any]] = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        raise DomainError(FailureCode.INTERNAL_ERROR)
    try:
        return TemplateFacts(
            duration_s=float(data["format"]["duration"]),
            fps=str(video["r_frame_rate"]),
            video_codec=str(video["codec_name"]),
            pix_fmt=str(video["pix_fmt"]),
            sample_rate=int(audio["sample_rate"]),
            channel_layout=str(audio["channel_layout"]),
        )
    except (KeyError, ValueError) as exc:
        raise DomainError(FailureCode.INTERNAL_ERROR) from exc


def read_template_facts(ffprobe: str, template: Path, timeout_seconds: float) -> TemplateFacts:
    """Probe ``template``; unreadable files raise a coded DomainError."""
    output = run_tool(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         "-i", str(template)],
        timeout_seconds,
    )  # fmt: skip
    try:
        return parse_facts(json.loads(output.stdout))
    except json.JSONDecodeError as exc:
        raise DomainError(FailureCode.INTERNAL_ERROR) from exc
