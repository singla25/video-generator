"""User-facing labels for the raw stages of a pending preview (T-PROG-BE). Pure Python."""

from __future__ import annotations

from collections.abc import Mapping

PREPARING = "preparing"
PREVIEW_STAGE_LABELS: Mapping[str, str] = {
    "fetch": PREPARING,
    "tts": "voice",
    "lipsync": "lipsync",
    "encode": "finishing",
    "check": "finishing",
    "publish": "finishing",
}


def pending_stage_label(raw: str | None) -> str:
    """The label shown for a pending preview's raw stage.

    No stage yet, or a raw name we do not know (including a label itself), reads as preparing.
    """
    return PREVIEW_STAGE_LABELS.get(raw or "", PREPARING)
