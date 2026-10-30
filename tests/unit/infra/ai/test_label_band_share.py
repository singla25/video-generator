"""The AI label band covers at least 10 % of the frame height (C2, D-M2-4).

The M2 Mac spike measured about 9 %. These tests pin the production code path: the renderer
helper, the render-time helper and the setting.
"""

from __future__ import annotations

import secrets
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from vidgen.infrastructure.ffmpeg.label import label_band_height
from vidgen.services.render_support import RenderConfig, band_height
from vidgen.settings import Settings

# Typical template heights: 720p, 1080p, 4:5 feed, vertical 1080x1920, 4K, odd sizes.
HEIGHTS = [240, 480, 720, 1080, 1350, 1920, 2160, 4320, 7, 1, 1001, 1917]


@pytest.mark.parametrize("height", HEIGHTS)
def test_label_band_is_at_least_ten_percent_of_frame_height(height: int) -> None:
    """M2-S8-P1: measured against the exact frame height, never rounded down below 10 %."""
    assert label_band_height(height) / height >= 0.10


@pytest.mark.parametrize("height", HEIGHTS)
def test_render_time_band_with_the_default_config_is_at_least_ten_percent(height: int) -> None:
    """M2-S8-P2: the number the encoder really uses (RenderConfig default share)."""
    share = RenderConfig(creator_entity="Org", pause_s=0.5).label_band_share
    assert band_height(height, share) / height >= 0.10


def test_a_nine_percent_band_would_fail_the_rule() -> None:
    """M2-S8-N1: guard against re-introducing the spike's ~9 % (1080p -> 97 px)."""
    assert band_height(1080, 0.09) / 1080 < 0.10  # documents what the rule rejects
    assert band_height(1080, 0.09) != label_band_height(1080)


@pytest.mark.parametrize("share", [0.09, 0.0, -0.1])
def test_settings_reject_a_label_share_below_ten_percent(share: float) -> None:
    """M2-S8-N2."""
    values: dict[str, Any] = {
        "creator_entity": "Org",
        "encryption_key": SecretStr(secrets.token_hex(32)),
        "index_key": SecretStr(secrets.token_hex(32)),
        "session_secret": SecretStr(secrets.token_hex(32)),
        "admin_password_hash": SecretStr("x"),
        "label_band_share": share,
    }
    with pytest.raises(ValidationError, match="label_band_share"):
        Settings(**values)
