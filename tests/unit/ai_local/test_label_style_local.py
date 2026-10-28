"""The local-AI path honours the label style (DD-32). LS-L-*."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.ai_local.conftest import make_settings
from vidgen.infrastructure.local_ai.factory import local_label_band_height


@pytest.mark.parametrize("frame_h", [1300, 1920, 1081])
def test_default_style_adds_no_band_height(tmp_path: Path, frame_h: int) -> None:
    """LS-L-P1: bubble is the default, so the local pipeline reserves no band."""
    assert local_label_band_height(make_settings(tmp_path, ai_mode="local"), frame_h) == 0


@pytest.mark.parametrize("frame_h", [1300, 1920])
def test_explicit_bubble_adds_no_band_height_whatever_the_share(
    tmp_path: Path, frame_h: int
) -> None:
    """LS-L-E1."""
    settings = make_settings(tmp_path, ai_mode="local", label_style="bubble", label_band_share=0.3)
    assert local_label_band_height(settings, frame_h) == 0


@pytest.mark.parametrize(("frame_h", "share", "expected"), [(1000, 0.10, 100), (1000, 0.25, 250)])
def test_band_style_honours_the_share(
    tmp_path: Path, frame_h: int, share: float, expected: int
) -> None:
    """LS-L-P2, LS-L-E1."""
    settings = make_settings(tmp_path, ai_mode="local", label_style="band", label_band_share=share)
    assert local_label_band_height(settings, frame_h) == expected
