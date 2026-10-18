"""Loudness matching helpers (EBU R128 / ITU-R BS.1770, B10)."""

from __future__ import annotations

import re

SILENCE_FLOOR_LUFS = -70.0  # ebur128 reports this for silence or too-short input
MAX_GAIN_DB = 24.0  # a safety bound; larger corrections mean something is wrong upstream
_INTEGRATED = re.compile(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS")


def parse_integrated_lufs(ebur128_stderr: str) -> float | None:
    """Return the final integrated loudness from ebur128 output, or None if unmeasurable."""
    found = _INTEGRATED.findall(ebur128_stderr)
    if not found:
        return None
    value = float(found[-1])
    return None if value <= SILENCE_FLOOR_LUFS else value


def gain_db(template_lufs: float | None, new_lufs: float | None) -> float:
    """Gain that brings the new audio to the template's loudness; 0 if either is unmeasurable."""
    if template_lufs is None or new_lufs is None:
        return 0.0
    return max(-MAX_GAIN_DB, min(MAX_GAIN_DB, template_lufs - new_lufs))
