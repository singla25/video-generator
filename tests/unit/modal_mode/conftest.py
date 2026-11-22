"""Fixtures for the Modal-mode tests: no network is allowed in any of them (AC7)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.fixtures.network import no_network  # noqa: F401  (re-exported fixture)
from tests.unit.ai_local.conftest import make_settings

ROOT = Path(__file__).resolve().parents[3]
APP_FILE = ROOT / "backend" / "modal_app" / "app.py"
VIDGEN_DIR = ROOT / "backend" / "vidgen"


@pytest.fixture(autouse=True)
def _offline(no_network: None) -> None:  # noqa: F811
    """Every test in this folder runs with sockets blocked."""


@pytest.fixture
def without_modal(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make ``import modal`` fail and forget a cached import; also no token variables."""
    monkeypatch.setitem(sys.modules, "modal", None)  # None in sys.modules => ImportError
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    yield


@pytest.fixture
def modal_settings(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Settings in modal mode with throwaway paths."""
    return make_settings(tmp_path, ai_mode="modal")
