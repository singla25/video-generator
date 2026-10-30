"""AC6: the AI label is at least 10 % of the frame height (spike measured ~9 %)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests.fixtures.assets import devanagari_font, latin_font
from tests.unit.ai_local.conftest import make_settings
from vidgen.infrastructure.ffmpeg.label import PillowLabelRenderer, label_band_height
from vidgen.infrastructure.local_ai.factory import local_label_band_height
from vidgen.services.render_support import band_height


@pytest.mark.parametrize("height", [1300, 1920, 1081, 1279, 2])
def test_band_height_is_at_least_ten_percent(height: int) -> None:
    assert label_band_height(height) >= 0.10 * height


@pytest.mark.parametrize("size", [(1080, 1300), (1080, 1920)])
def test_rendered_png_in_a_real_frame_is_at_least_ten_percent(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    width, height = size
    band = label_band_height(height)
    out = tmp_path / "label.png"
    PillowLabelRenderer(devanagari_font(), latin_font()).render_label(width, band, out)
    with Image.open(out) as image:
        assert image.size == (width, band)
        assert image.height / height >= 0.10


@pytest.mark.parametrize("height", [1300, 1920])
def test_service_band_height_with_default_share_is_at_least_ten_percent(height: int) -> None:
    assert band_height(height, 0.10) >= 0.10 * height


@pytest.mark.parametrize("frame_h", [1300, 1920])
def test_local_pipeline_never_shrinks_the_band_below_ten_percent(
    tmp_path: Path, frame_h: int
) -> None:
    """The local assembler must size the band with the same rule as the fake path."""
    settings = make_settings(tmp_path, ai_mode="local", label_style="band")
    assert local_label_band_height(settings, frame_h) >= 0.10 * frame_h
