"""scripts/setup.py writes how many worker containers to start (P2: local mode has none)."""

from __future__ import annotations

import pytest

from tests.unit.meta.conftest import Harness
from tests.unit.meta.test_setup_installer import read_settings


@pytest.mark.parametrize(("mode", "workers"), [("fake", "1"), ("local", "0"), ("modal", "1")])
def test_docker_worker_count_follows_the_mode(harness: Harness, mode: str, workers: str) -> None:
    harness.answers["mode"] = [mode]
    assert harness.run_main() == 0
    assert read_settings(harness.dotenv)["VIDGEN_DOCKER_WORKERS"] == workers
