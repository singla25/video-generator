"""Settings -> render config -> label renderer, by style (DD-32). LS-P-P3."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.api.conftest import make_settings
from vidgen.worker.runner import render_config

URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen_test"


def test_render_config_defaults_to_the_bubble(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LS-P-P3."""
    monkeypatch.delenv("VIDGEN_LABEL_STYLE", raising=False)
    assert render_config(make_settings(URL, tmp_path)).label_style == "bubble"


@pytest.mark.parametrize("style", ["bubble", "band"])
def test_render_config_copies_the_label_style(tmp_path: Path, style: str) -> None:
    """LS-P-P3."""
    assert render_config(make_settings(URL, tmp_path, label_style=style)).label_style == style
