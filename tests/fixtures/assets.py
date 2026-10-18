"""Locate bundled assets for tests. Fails loudly (does not skip) when an asset is missing."""

from __future__ import annotations

from pathlib import Path

import pytest

FONT_DIR = Path(__file__).resolve().parents[2] / "backend" / "vidgen" / "assets" / "fonts"


def devanagari_font() -> Path:
    """Path of the Noto Sans Devanagari font, or fail the test with instructions."""
    candidates = sorted(FONT_DIR.glob("*.ttf")) + sorted(FONT_DIR.glob("*.otf"))
    if not candidates:
        pytest.fail(
            f"Devanagari font missing: place Noto Sans Devanagari (.ttf) in {FONT_DIR} "
            "(Admin supplies it; see plan 'Font asset')."
        )
    return candidates[0]
