"""Locate bundled assets for tests. Fails loudly (does not skip) when an asset is missing."""

from __future__ import annotations

from pathlib import Path

import pytest

FONT_DIR = Path(__file__).resolve().parents[2] / "backend" / "vidgen" / "assets" / "fonts"


def _find(pattern: str, what: str) -> Path:
    """First font file in the assets folder matching ``pattern``, else fail the test."""
    matches = sorted(FONT_DIR.glob(pattern))
    if not matches:
        pytest.fail(
            f"{what} font missing: place a file matching '{pattern}' in {FONT_DIR} "
            "(the Admin supplies the Noto fonts; see the plan, 'Font asset')."
        )
    return matches[0]


def devanagari_font() -> Path:
    """Noto Sans Devanagari (``NotoSansDevanagari-*.ttf``)."""
    return _find("NotoSansDevanagari*.ttf", "Devanagari")


def latin_font() -> Path:
    """Noto Sans for Latin text (``NotoSans-*.ttf``; does not match the Devanagari file)."""
    return _find("NotoSans-*.ttf", "Latin")
