"""Real output quality check: format, length and slot loudness against the template (AC8, AC9).

The checker reports problems as ``QualityIssue`` codes and never raises for bad media. Neither
messages nor logs contain file names or paths (the tool runner logs only the tool name).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from vidgen.domain.codes import DomainError
from vidgen.domain.quality import OutputExpectation, QualityIssue
from vidgen.domain.timing import duration_within_tolerance
from vidgen.infrastructure.ffmpeg import loudness
from vidgen.infrastructure.ffmpeg.facts import probe_json, sibling_ffprobe

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 600.0
DEFAULT_DURATION_TOLERANCE_MS = 50
DEFAULT_LOUDNESS_TOLERANCE_LU = 1.0
_NO_FILTER = "anull"


@dataclass(frozen=True)
class _Media:
    """The parts of an ffprobe result the checks compare."""

    duration_s: float
    video: dict[str, Any]
    audio: dict[str, Any] | None


def _media(data: dict[str, Any]) -> _Media:
    """Pick the first video and audio stream; a file without video is unreadable."""
    streams: list[dict[str, Any]] = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ValueError("no video stream")
    return _Media(float(data["format"]["duration"]), video, audio)


class OutputQualityChecker:
    """Compares a rendered output with its template using ffprobe and ebur128."""

    def __init__(
        self,
        ffmpeg_path: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_S,
        duration_tolerance_ms: int = DEFAULT_DURATION_TOLERANCE_MS,
        loudness_tolerance_lu: float = DEFAULT_LOUDNESS_TOLERANCE_LU,
        *,
        ffprobe_path: str | None = None,
    ) -> None:
        self._ffmpeg = ffmpeg_path
        self._ffprobe = ffprobe_path or sibling_ffprobe(ffmpeg_path)
        self._timeout = timeout_seconds
        self._duration_tolerance_ms = duration_tolerance_ms
        self._loudness_tolerance_lu = loudness_tolerance_lu

    def check(
        self, template: Path, output: Path, expected: OutputExpectation | None = None
    ) -> list[str]:
        """Return the issue codes found; an empty list means the output passed. Never raises."""
        try:
            if not output.is_file():
                return [QualityIssue.UNREADABLE_OUTPUT]
            if output.stat().st_size == 0:
                return [QualityIssue.EMPTY_OUTPUT]
            return self._compare(template, output, expected)
        except (DomainError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
            logger.warning("output could not be checked")
            return [QualityIssue.UNREADABLE_OUTPUT]

    def _compare(
        self, template: Path, output: Path, expected: OutputExpectation | None
    ) -> list[str]:
        """Run every check and collect the codes (each at most once)."""
        want = _media(probe_json(self._ffprobe, template, self._timeout))
        got = _media(probe_json(self._ffprobe, output, self._timeout))
        issues = _format_issues(want, got)
        if expected is not None and not duration_within_tolerance(
            got.duration_s, want.duration_s, expected.delta_s, self._duration_tolerance_ms
        ):
            issues.append(QualityIssue.DURATION_MISMATCH)
        if got.audio is not None:
            issues.extend(self._loudness_issues(template, output, expected))
        codes = list(dict.fromkeys(str(issue) for issue in issues))
        if codes:
            logger.warning("output differs from template", extra={"issues": ",".join(codes)})
        return codes

    def _loudness_issues(
        self, template: Path, output: Path, expected: OutputExpectation | None
    ) -> list[QualityIssue]:
        """Silence of the output, and loudness of each slot region against the template's."""
        if expected is None or not expected.regions:
            silent = self._lufs(output, None) is None
            return [QualityIssue.AUDIO_SILENT] if silent else []
        issues: list[QualityIssue] = []
        for region in expected.regions:
            wanted = self._lufs(template, region.template)
            if wanted is None:
                continue  # the template is quiet there: nothing to compare with
            actual = self._lufs(output, region.output)
            if actual is None:
                issues.append(QualityIssue.AUDIO_SILENT)
            elif abs(actual - wanted) > self._loudness_tolerance_lu:
                issues.append(QualityIssue.LOUDNESS_MISMATCH)
        return issues

    def _lufs(self, path: Path, region: tuple[float, float] | None) -> float | None:
        """Integrated loudness of ``path`` (or of one region of it)."""
        window: list[str] = []
        if region is not None:
            start, end = region
            window = ["-ss", f"{start:.6f}", "-t", f"{end - start:.6f}"]
        return loudness.measure_lufs(
            self._ffmpeg, [*window, "-i", str(path)], _NO_FILTER, self._timeout
        )


def _format_issues(want: _Media, got: _Media) -> list[QualityIssue]:
    """Differences in resolution, frame rate, video codec and audio format."""
    issues: list[QualityIssue] = []
    if (want.video["width"], want.video["height"]) != (got.video["width"], got.video["height"]):
        issues.append(QualityIssue.RESOLUTION_MISMATCH)
    if Fraction(want.video["r_frame_rate"]) != Fraction(got.video["r_frame_rate"]):
        issues.append(QualityIssue.FPS_MISMATCH)
    if want.video["codec_name"] != got.video["codec_name"]:
        issues.append(QualityIssue.VIDEO_CODEC_MISMATCH)
    if want.audio is not None and (
        got.audio is None or _audio_format(want.audio) != _audio_format(got.audio)
    ):
        issues.append(QualityIssue.AUDIO_FORMAT_MISMATCH)
    return issues


def _audio_format(audio: dict[str, Any]) -> tuple[str, str, int]:
    """Codec, sample rate and channel count."""
    return (str(audio["codec_name"]), str(audio["sample_rate"]), int(audio["channels"]))
