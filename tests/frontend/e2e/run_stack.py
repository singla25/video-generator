"""Run the Playwright E2E suite against a real, throwaway stack, then tear everything down.

Starts: a throwaway Postgres database (Alembic upgrade head), the API (uvicorn, ai_backend=fake),
one Dramatiq worker (unique queue name on Redis db 7) and the Vite dev server. Secrets are random
test values passed through the environment; no .env file and never the dev database ``vidgen``.
Everything started here is stopped and the database removed in ``finally``.

Usage (repository root): uv run python tests/frontend/e2e/run_stack.py [playwright args...]
"""

# ruff: noqa: S603, S607
from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher

from tests.fixtures.templates import make_template

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"
ADMIN_DSN = "postgresql://vidgen:devpassword@127.0.0.1:5432/postgres"
SQLA_PREFIX = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/"
PASSWORD = "e2e-" + secrets.token_hex(6)
WEB = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000"
SCREENSHOTS = ROOT / "media" / "review" / "ui"


def wait_for(url: str, timeout: float = 60.0) -> None:
    """Poll ``url`` until it answers (any HTTP status below 500)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)  # noqa: S310 - fixed local URL
            return
        except urllib.error.HTTPError as err:
            if err.code < 500:
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}")


def main() -> int:
    """Create the stack, run Playwright, always clean up."""
    suffix = secrets.token_hex(4)
    db_name = f"vidgen_e2e_{suffix}_test"
    work = Path(tempfile.mkdtemp(prefix="vidgen-e2e-"))
    fixtures = work / "fixtures"
    fixtures.mkdir()
    procs: list[subprocess.Popen[bytes]] = []
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "VIDGEN_CREATOR_ENTITY": "E2E Test Org",
        "VIDGEN_ENCRYPTION_KEY": secrets.token_hex(32),
        "VIDGEN_INDEX_KEY": secrets.token_hex(32),
        "VIDGEN_SESSION_SECRET": secrets.token_hex(32),
        "VIDGEN_ADMIN_PASSWORD_HASH": PasswordHasher().hash(PASSWORD),
        "VIDGEN_DATABASE_URL": SQLA_PREFIX + db_name,
        "VIDGEN_REDIS_URL": "redis://127.0.0.1:6379/7",
        "VIDGEN_QUEUE_NAME": f"vidgen_e2e_{suffix}",
        "VIDGEN_STORAGE_ROOT": str(work / "media"),
        "VIDGEN_AI_BACKEND": "fake",
        "VIDGEN_COOKIE_SECURE": "false",
        "NODE_PATH": str(FRONTEND / "node_modules"),  # specs live outside frontend/
        "E2E_BASE_URL": WEB,
        "E2E_ADMIN_PASSWORD": PASSWORD,
        "E2E_FIXTURES": str(fixtures),
        "E2E_SCREENSHOTS": str(SCREENSHOTS),
    }
    code = 1
    try:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{db_name}"')
        config = Config(str(ROOT / "backend" / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", SQLA_PREFIX + db_name)
        command.upgrade(config, "head")

        make_template(fixtures / "template.mp4", seconds=4.0)
        (fixtures / "consent.pdf").write_bytes(b"%PDF-1.4\n%synthetic consent\n%%EOF\n")
        (fixtures / "sheet.csv").write_text(
            "Voter Name,Voter ID\n"
            "Asha Verma,E2E000001\n"
            "अनुराधा शर्मा,E2E000002\n"
            "Chand Test,E2E000003\n"
            ",E2E000004\n"
            "Esha Test,E2E000001\n",
            encoding="utf-8",
        )
        (fixtures / "corrupt.mp4").write_bytes(b"this is not a video" * 200)

        py = sys.executable
        api = subprocess.Popen(
            [py, str(Path(__file__).with_name("serve_api.py"))], env=env, cwd=ROOT
        )
        worker = subprocess.Popen([py, "-m", "vidgen.worker"], env=env, cwd=ROOT)
        procs += [api, worker]
        vite = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
            env=env,
            cwd=FRONTEND,
            start_new_session=True,  # so the whole npm/vite tree can be stopped as a group
        )
        procs.append(vite)
        wait_for(API + "/health")
        wait_for(WEB + "/")

        args = sys.argv[1:] or []
        pw = subprocess.run(
            ["npx", "playwright", "test", "--workers=1", *args], env=env, cwd=FRONTEND
        )
        code = pw.returncode
    finally:
        for proc in reversed(procs):
            if proc.poll() is None:
                if proc.args and proc.args[0] == "npm":
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.send_signal(signal.SIGINT)
        for proc in procs:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
