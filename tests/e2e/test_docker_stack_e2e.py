"""Real containers: build the images, start profile ``app`` in a SEPARATE compose project.

Isolation: own project name, own host ports, own temp media folder and a demo settings file with
made-up values. The default project, its volumes and the real settings file are never touched.
Skipped when Docker is not available. No migrations are run.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.unit.meta.conftest import ROOT

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

PROJECT = "vidgen-t3test"
BUILD_TIMEOUT_S = 1800
HEALTH_TIMEOUT_S = 180


def docker_available() -> bool:
    """True when the docker CLI exists and the daemon answers."""
    docker = shutil.which("docker")
    if docker is None:
        return False
    return subprocess.run([docker, "info"], capture_output=True, check=False).returncode == 0  # noqa: S603


def free_port() -> int:
    """A currently free loopback port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


DEMO_SETTINGS = "\n".join(
    [
        "VIDGEN_CREATOR_ENTITY='Demo'",
        f"VIDGEN_ENCRYPTION_KEY={'ab' * 32}",
        f"VIDGEN_INDEX_KEY={'cd' * 32}",
        "VIDGEN_SESSION_SECRET=demo-session-secret-not-real",
        "VIDGEN_ADMIN_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZGVtby1oYXNo'",
        "VIDGEN_DATABASE_URL=postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen",
        "VIDGEN_REDIS_URL=redis://127.0.0.1:6379/0",
        "VIDGEN_STORAGE_ROOT=./media",
        "VIDGEN_AI_MODE=fake",
        "VIDGEN_COOKIE_SECURE=false",
        "",
    ]
)


class Stack:
    """Handle on the isolated compose project."""

    def __init__(self, settings: Path, media: Path) -> None:
        self.api_port = free_port()
        self.dashboard_port = free_port()
        self.vars = {
            "VIDGEN_ENV_FILE": str(settings),
            "VIDGEN_MEDIA_DIR": str(media),
            "VIDGEN_API_PORT": str(self.api_port),
            "VIDGEN_DASHBOARD_PORT": str(self.dashboard_port),
            "VIDGEN_DB_PORT": str(free_port()),
            "VIDGEN_REDIS_PORT": str(free_port()),
            "VIDGEN_DOCKER_WORKERS": "1",
        }

    def compose(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
        """Run ``docker compose`` for the test project and profile ``app``."""
        return subprocess.run(  # noqa: S603
            [
                shutil.which("docker") or "docker",
                "compose",
                "-p",
                PROJECT,
                "--profile",
                "app",
                *args,
            ],
            cwd=ROOT,
            env={**os.environ, **self.vars},
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    """Build and start the app profile; always tear down only this project and its volumes."""
    if not docker_available():
        pytest.skip("docker is not available")
    work = tmp_path_factory.mktemp("docker-stack")
    settings = work / "demo-settings"
    settings.write_text(DEMO_SETTINGS, encoding="utf-8")
    media = work / "media"
    media.mkdir()
    handle = Stack(settings, media)
    try:
        built = handle.compose("up", "-d", "--build", timeout=BUILD_TIMEOUT_S)
        assert built.returncode == 0, built.stderr[-2000:]
        yield handle
    finally:
        handle.compose("down", "-v", "--remove-orphans")


def fetch(url: str) -> int | None:
    """HTTP status of ``url`` or None while it is not reachable."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - loopback test URL
            return int(response.status)
    except (urllib.error.URLError, OSError):
        return None


def test_health_endpoint_answers_through_the_dashboard_api_forward(stack: Stack) -> None:
    url = f"http://127.0.0.1:{stack.dashboard_port}/api/health"
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    status = fetch(url)
    while status != 200 and time.monotonic() < deadline:
        time.sleep(3)
        status = fetch(url)
    assert status == 200


def test_pillow_raqm_layout_is_available_inside_the_worker_image(stack: Stack) -> None:
    code = "from PIL import features; print(features.check('raqm'))"
    done = stack.compose(
        "run", "--rm", "--no-deps", "-T", "--entrypoint", "python", "worker", "-c", code
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "True"
