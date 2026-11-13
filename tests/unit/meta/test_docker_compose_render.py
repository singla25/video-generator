"""Rendered compose config: which service really receives the Modal tokens (P4).

``docker compose config`` needs the docker CLI but no daemon. The rendered config contains
settings, so it is parsed and never printed or put in an assertion message.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

import pytest

from tests.unit.meta.conftest import ROOT

DOCKER = shutil.which("docker")
pytestmark = pytest.mark.skipif(DOCKER is None, reason="docker CLI is not installed")

DEMO_ID = "demo-id"
DEMO_SECRET = "demo-secret"  # noqa: S105


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Services of the rendered app profile with only VIDGEN_ENV_FILE pointing to demo tokens."""
    settings = tmp_path_factory.mktemp("render") / "demo-settings"
    settings.write_text(
        f"MODAL_TOKEN_ID={DEMO_ID}\nMODAL_TOKEN_SECRET={DEMO_SECRET}\n", encoding="utf-8"
    )
    child = {k: v for k, v in os.environ.items() if not k.startswith("MODAL_")}
    child["VIDGEN_ENV_FILE"] = str(settings)
    done = subprocess.run(  # noqa: S603
        [
            DOCKER or "docker",
            "compose",
            "-p",
            "vidgen-cfgtest",
            "--profile",
            "app",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=child,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, "docker compose config failed (output withheld: it holds settings)"
    services: dict[str, Any] = json.loads(done.stdout)["services"]
    return services


def token(rendered: dict[str, Any], service: str, name: str) -> str | None:
    """The rendered value of one token variable (None when absent or null)."""
    value = (rendered[service].get("environment") or {}).get(name)
    return None if value is None else str(value)


@pytest.mark.parametrize("name", ["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"])
def test_worker_gets_the_demo_tokens_from_the_settings_file_alone(
    rendered: dict[str, Any], name: str
) -> None:
    expected = DEMO_ID if name.endswith("ID") else DEMO_SECRET
    assert token(rendered, "worker", name) == expected


@pytest.mark.parametrize("name", ["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"])
def test_api_gets_blank_tokens_even_though_the_settings_file_has_them(
    rendered: dict[str, Any], name: str
) -> None:
    assert token(rendered, "api", name) == ""


@pytest.mark.parametrize("name", ["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"])
def test_dashboard_gets_no_tokens(rendered: dict[str, Any], name: str) -> None:
    assert token(rendered, "dashboard", name) in (None, "")
