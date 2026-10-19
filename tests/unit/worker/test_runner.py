"""Worker process wiring helpers (settings -> render config -> renderer)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.integration.api.conftest import make_settings
from vidgen.domain.retry import RetryPolicy
from vidgen.domain.timing import TimingRules
from vidgen.services.render_row import RenderConfig, RowRenderer
from vidgen.worker.runner import FONT_DIR, build_renderer, render_config

URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen_test"


class Sink:
    """PreviewSink that ignores everything."""

    def preview_rendered(self, batch_id: object, key: str) -> None:
        """Ignore."""

    def preview_failed(self, batch_id: object, code: object) -> None:
        """Ignore."""


def test_render_config_copies_the_rendering_settings(tmp_path: Path) -> None:
    """Settings -> RenderConfig: creator, pause, timing rules and retry policy."""
    settings = make_settings(
        URL,
        tmp_path,
        creator_entity="Example Org",
        pause_seconds=0.75,
        max_stretch_ratio=0.1,
        max_extension_seconds=1.0,
        crossfade_ms=40,
        row_timeout_seconds=90,
        retry_delay_seconds=3,
        max_retries=2,
    )
    config = render_config(settings)
    assert isinstance(config, RenderConfig)
    assert config.creator_entity == "Example Org"
    assert config.pause_s == 0.75
    assert config.timing == TimingRules(max_stretch_ratio=0.1, max_extension_s=1.0, crossfade_ms=40)
    assert config.retry == RetryPolicy(timeout_seconds=90, delay_seconds=3, max_retries=2)


def test_render_config_defaults_follow_the_plan(tmp_path: Path) -> None:
    """B8: 600 s, 10 s, one retry; D16: 15 % stretch, 1.5 s extension, 30 ms crossfade."""
    config = render_config(make_settings(URL, tmp_path))
    assert config.retry == RetryPolicy(timeout_seconds=600, delay_seconds=10, max_retries=1)
    assert config.timing == TimingRules(
        max_stretch_ratio=0.15, max_extension_s=1.5, crossfade_ms=30
    )


def test_build_renderer_wires_the_fake_ai_backend(tmp_path: Path) -> None:
    """ai_backend=fake gives a RowRenderer without touching the database or ffmpeg."""
    renderer = build_renderer(make_settings(URL, tmp_path, ai_backend="fake"), Sink())  # type: ignore[arg-type]
    assert isinstance(renderer, RowRenderer)


def test_build_renderer_refuses_the_real_backend_until_m2(tmp_path: Path) -> None:
    """Real AI adapters arrive in M2; a clear error beats a silent fake."""
    with pytest.raises(RuntimeError, match="M2"):
        build_renderer(make_settings(URL, tmp_path, ai_backend="real"), Sink())  # type: ignore[arg-type]


def test_both_label_fonts_ship_with_the_package() -> None:
    """The worker image needs the fonts next to the code."""
    assert (FONT_DIR / "NotoSansDevanagari-Bold.ttf").is_file()
    assert (FONT_DIR / "NotoSans-Bold.ttf").is_file()


def test_python_dash_m_entry_point_exposes_run_without_starting_anything() -> None:
    """Importing the module must not start a worker (only `python -m` does)."""
    module = importlib.import_module("vidgen.worker.__main__")
    assert callable(module.run)
