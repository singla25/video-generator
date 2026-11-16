"""Guided installer: checks the tools, writes the settings file, sets the admin login.

    python3 scripts/setup.py [--root PATH]

Standard library only, so it runs on a bare python3 before any dependency is installed.
Password hashing is delegated to ``scripts/dev_setup.py hash-password`` through ``uv run`` (the
password goes over stdin, never on a command line). Secrets are never printed or logged, and the
Modal token pair reaches child processes only through their environment. Migrations run only
after an explicit "y".
"""

import argparse
import ast
import getpass
import os
import secrets
import subprocess
import sys
import tempfile
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DOTENV_NAME = "." + "env"
REQUIRED_TOOLS = ("docker", "uv", "node", "ffmpeg")
MODES = ("fake", "local", "modal")
MIN_PASSWORD_CHARS = 12
FILE_MODE = 0o600
EXIT_FAILURE = 1
EXIT_NO_TERMINAL = 2
EXIT_INTERRUPTED = 130
MODAL_LINKS = ("https://modal.com/signup", "https://modal.com/settings/tokens")
DATABASE_URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen"
REDIS_URL = "redis://127.0.0.1:6379/0"
COMPOSE_COMMAND = "docker compose --profile app up -d"
HASH_KEY = "VIDGEN_ADMIN_PASSWORD_HASH"
WORKERS_KEY = "VIDGEN_DOCKER_WORKERS"
UNSAFE_VALUE_CHARS = "'\"`\r\n \t"
# Keys that protect stored data: losing them makes existing encrypted rows unreadable.
KEPT_KEYS = ("VIDGEN_ENCRYPTION_KEY", "VIDGEN_INDEX_KEY")

# No ``from __future__ import annotations``: the tests load this file without registering it in
# sys.modules, which ``@dataclass`` needs to resolve string annotations.
Runner = Callable[..., subprocess.CompletedProcess[str]]


class InstallerError(Exception):
    """A problem the user can fix; its message is safe to show (it never holds a secret)."""


@dataclass
class Seams:
    """Every outside effect of the installer, injectable so tests need no real tools."""

    which: Callable[[str], str | None]
    run: Runner
    getpass: Callable[[str], str]
    ask: Callable[[str], str]
    open_url: Callable[[str], bool]
    echo: Callable[[str], None]
    is_interactive: Callable[[], bool]


def _real_run(
    argv: Sequence[str],
    *,
    extra_vars: Mapping[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output; ``extra_vars`` are added to the child's environment."""
    env = {**os.environ, **(extra_vars or {})}
    return subprocess.run(  # noqa: S603
        list(argv), input=input_text, text=True, capture_output=True, env=env, check=False
    )


def real_seams() -> Seams:
    """The seams used when the installer runs for real."""
    import shutil

    return Seams(
        which=shutil.which,
        run=_real_run,
        getpass=getpass.getpass,
        ask=input,
        open_url=webbrowser.open,
        echo=print,
        is_interactive=lambda: sys.stdin.isatty() and sys.stdout.isatty(),
    )


def check_prerequisites(seams: Seams) -> None:
    """Fail naming every missing tool, or a Docker that is installed but not running."""
    missing = [tool for tool in REQUIRED_TOOLS if seams.which(tool) is None]
    if missing:
        for tool in missing:
            seams.echo(f"Missing tool: {tool}. Please install it and run this installer again.")
        raise InstallerError("Some required tools are missing.")
    if seams.run(["docker", "info"]).returncode != 0:
        raise InstallerError("Docker is installed but is not running. Start Docker and try again.")


FALLBACK_MODES = ("fake", "local")
BACKEND_SETTINGS = Path("backend") / "vidgen" / "settings.py"


def accepted_modes(root: Path) -> tuple[str, ...]:
    """Modes the backend accepts: the ``ai_mode: Literal[...]`` values, read with ``ast``.

    The backend is parsed, never imported, so its dependencies are not needed. Anything missing
    or unexpected falls back to the modes that always work.
    """
    try:
        tree = ast.parse((root / BACKEND_SETTINGS).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return FALLBACK_MODES
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "ai_mode"
            and isinstance(node.annotation, ast.Subscript)
            and isinstance(node.annotation.value, ast.Name)
            and node.annotation.value.id == "Literal"
        ):
            arg = node.annotation.slice
            items = arg.elts if isinstance(arg, ast.Tuple) else [arg]
            values = tuple(
                i.value for i in items if isinstance(i, ast.Constant) and isinstance(i.value, str)
            )
            return values or FALLBACK_MODES
    return FALLBACK_MODES


def choose_mode(seams: Seams, root: Path) -> str:
    """Ask for the AI mode until the answer is one the backend accepts (case/spaces ignored)."""
    offered = tuple(m for m in MODES if m in accepted_modes(root))
    while True:
        prompt = f"Which AI mode do you want? Type {', '.join(offered)}: "
        answer = seams.ask(prompt).strip().lower()
        if answer in offered:
            return answer
        if answer in MODES:
            seams.echo(f"The {answer} mode is not available yet (see ADR-013).")
        seams.echo(f"Please type one of: {', '.join(offered)}.")


def collect_modal_tokens(seams: Seams) -> tuple[str, str]:
    """Show the account steps and privacy notice, then read and check the token pair."""
    seams.echo("Modal setup steps:")
    seams.echo("  1. Sign up for a free Modal account.")
    seams.echo("  2. Create a token (you get a token ID and a token secret).")
    seams.echo("  3. Paste both here; they are hidden while you type.")
    for url in MODAL_LINKS:
        seams.echo(f"  {url}")
        seams.open_url(url)
    seams.echo(
        "Privacy: in this mode the names, voices and faces of your templates are sent to Modal."
    )
    token_id = seams.getpass("Modal token ID (hidden): ").strip()
    token_secret = seams.getpass("Modal token secret (hidden): ").strip()
    if not token_id or not token_secret:
        raise InstallerError("The Modal token ID and token secret must both be filled in.")
    if any(ch in value for value in (token_id, token_secret) for ch in UNSAFE_VALUE_CHARS):
        raise InstallerError("A Modal token must not contain spaces or quotes. Paste it again.")
    check = seams.run(
        ["uv", "run", "--with", "modal", "modal", "token", "info"],
        extra_vars={"MODAL_TOKEN_ID": token_id, "MODAL_TOKEN_SECRET": token_secret},
    )
    if check.returncode != 0:
        raise InstallerError(
            "Modal could not accept this token pair (invalid, rejected, or Modal could not be "
            "reached). Check the token and your connection."
        )
    return token_id, token_secret


def hash_admin_password(seams: Seams, root: Path) -> str:
    """Read the password twice (hidden) and return its argon2 hash from dev_setup.py."""
    password = seams.getpass(f"Admin password (at least {MIN_PASSWORD_CHARS} characters): ")
    if len(password) < MIN_PASSWORD_CHARS:
        raise InstallerError(f"Use at least {MIN_PASSWORD_CHARS} characters.")
    if seams.getpass("Type it again to confirm: ") != password:
        raise InstallerError("The two entries differ. Nothing was written.")
    script = str(root / "scripts" / "dev_setup.py")
    done = seams.run(["uv", "run", "python", script, "hash-password"], input_text=password + "\n")
    hashed = done.stdout.strip() if isinstance(done.stdout, str) else ""
    if done.returncode != 0 or not hashed:
        raise InstallerError("Could not hash the admin password.")
    return hashed


def read_kept_keys(path: Path) -> dict[str, str]:
    """The data-protecting keys of an existing settings file (never printed or logged)."""
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        value = value.strip().strip("'\"")
        if sep and key.strip() in KEPT_KEYS and value:
            found[key.strip()] = value
    return found


def render_settings(
    mode: str,
    admin_hash: str,
    tokens: tuple[str, str] | None,
    kept: Mapping[str, str] | None = None,
) -> str:
    """The text of the settings file: fresh random secrets, local services, chosen mode."""
    kept = kept or {}
    lines = [
        "# Generated by scripts/setup.py. Git-ignored: never commit.",
        "VIDGEN_CREATOR_ENTITY='Local Dev'",
        f"VIDGEN_ENCRYPTION_KEY={kept.get('VIDGEN_ENCRYPTION_KEY') or secrets.token_hex(32)}",
        f"VIDGEN_INDEX_KEY={kept.get('VIDGEN_INDEX_KEY') or secrets.token_hex(32)}",
        f"VIDGEN_SESSION_SECRET={secrets.token_urlsafe(48)}",
        f"{HASH_KEY}='{admin_hash}'",
        f"VIDGEN_DATABASE_URL={DATABASE_URL}",
        f"VIDGEN_REDIS_URL={REDIS_URL}",
        "VIDGEN_STORAGE_ROOT=./media",
        f"VIDGEN_AI_MODE={mode}",
        "VIDGEN_COOKIE_SECURE=false",
        # Local mode runs the worker on the host (real models need the GPU), so no container.
        f"{WORKERS_KEY}={'0' if mode == 'local' else '1'}",
    ]
    if tokens is not None:
        lines += [f"MODAL_TOKEN_ID='{tokens[0]}'", f"MODAL_TOKEN_SECRET='{tokens[1]}'"]
    return "\n".join([*lines, ""])


def write_private(path: Path, text: str) -> None:
    """Write ``text`` atomically with owner-only permissions; no temp file survives a failure."""
    handle, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=DOTENV_NAME + ".tmp.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as tmp:
            tmp.write(text)
        os.chmod(tmp_name, FILE_MODE)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def maybe_migrate(seams: Seams, root: Path) -> None:
    """Apply database migrations only after an explicit "y"."""
    answer = seams.ask("Apply database migrations now? [y/N] ").strip().lower()
    if answer != "y":
        seams.echo("Skipped migrations. Apply them later when you are ready.")
        return
    done = seams.run(
        ["uv", "run", "alembic", "-c", str(root / "backend" / "alembic.ini"), "upgrade", "head"],
        extra_vars={"VIDGEN_DATABASE_URL": DATABASE_URL},
    )
    if done.returncode != 0:
        raise InstallerError("The database migration failed. Your settings file was kept.")
    seams.echo("Database migrations applied.")


def install(root: Path, seams: Seams) -> int:
    """The whole guided flow; returns the exit code."""
    if not seams.is_interactive():
        raise InstallerError("This installer needs a terminal to ask you questions.")
    check_prerequisites(seams)
    target = root / DOTENV_NAME
    kept: dict[str, str] = {}
    if target.exists():
        answer = seams.ask("A settings file already exists. Overwrite it? [y/N] ")
        if answer.strip().lower() != "y":
            seams.echo("Kept your existing settings file. Nothing was changed.")
            return 0
        kept = read_kept_keys(target)
    mode = choose_mode(seams, root)
    tokens = collect_modal_tokens(seams) if mode == "modal" else None
    admin_hash = hash_admin_password(seams, root)
    write_private(target, render_settings(mode, admin_hash, tokens, kept))
    seams.echo("Settings file written (owner-only permissions).")
    maybe_migrate(seams, root)
    seams.echo(f"Next: {COMPOSE_COMMAND}")
    return 0


def main(argv: Sequence[str] | None = None, seams: Seams | None = None) -> int:
    """Entry point; returns 0 on success, non-zero with a clear message otherwise."""
    parser = argparse.ArgumentParser(description="Guided installer for the video generator.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args(argv)
    active = seams or real_seams()
    try:
        return install(Path(args.root), active)
    except InstallerError as error:
        active.echo(f"Error: {error}")
        return EXIT_NO_TERMINAL if not active.is_interactive() else EXIT_FAILURE
    except EOFError:
        active.echo("Input was closed before the questions were answered. Nothing was written.")
        return EXIT_FAILURE
    except KeyboardInterrupt:
        active.echo("Cancelled. Nothing was written.")
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    raise SystemExit(main())
