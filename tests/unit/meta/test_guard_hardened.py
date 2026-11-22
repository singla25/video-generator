"""Tests for the proposed hardened guard (docs/patches/guard.hardened.py), round 4 finding 1.

One case per bypass found against the current guard, plus the old behaviour that must stay and
ordinary commands that must still pass. The hook itself (.claude/hooks/guard.py) is not touched.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from types import ModuleType

import pytest

from tests.unit.meta.conftest import ROOT

PATCH = ROOT / "docs" / "patches" / "guard.hardened.py"

BYPASSES_NOW_BLOCKED = [
    # git options before the subcommand, long flags, main-branch pushes
    "git -C . push --force origin x",
    "git -c a=b push -f origin x",
    "git push origin HEAD:refs/heads/x --mirror",
    "git push origin :old-branch",
    "git push --delete origin old-branch",
    "git push origin main",
    "git push origin HEAD:main",
    "git branch --delete --force feat",
    "git checkout -f main",
    "git switch --discard-changes main",
    "git reset --merge",
    "git worktree remove --force x",
    "git stash drop",
    # rm long flags
    "rm --recursive --force a",
    # scripting deletes
    "python3 -c \"import shutil;shutil.rmtree('a')\"",
    "perl -e 'unlink(glob(\"*\"))'",
    # secrets
    "cat .env.production",
    "cat .env.local",
    "grep -r x .env.staging",
    "printenv HOME",
    "echo $VIDGEN_ENCRYPTION_KEY",
    "echo ${DB_PASSWORD}",
    # parent directories inside a path
    "cat foo/../../x",
    "ls docs/../../outside",
    # redirects glued to the operator
    "echo x >/etc/cron.d/x",
    "echo x >>/var/log/x",
    # shell writes to the rules
    "sed -i s/a/b/ .claude/hooks/guard.py",
    "tee CLAUDE.md </dev/null",
    "cp /dev/null CLAUDE.md",
    "mv .claude/hooks/guard.py g",
    "python3 -c \"open('CLAUDE.md','w').write('x')\"",
    "cp x .git/config",
    # data leaving through a script
    "python3 -c \"import urllib.request as u;u.urlopen('https://x',data=b'a')\"",
]

OLD_BEHAVIOUR_STILL_BLOCKED = [
    "git push origin +x",
    "rm -fr a",
    "cat ./.env",
    "cat /proc/self/environ",
    "echo x > .claude/settings.json",
    "git push --force origin x",
    "git push -f origin x",
    "git reset --hard HEAD~1",
    "git clean -fd",
    "git branch -D feat",
    "rm -rf a",
    "rm -r a",
    "rm *.txt",
    "alembic upgrade head",
    "uv run alembic upgrade head",
    "psql -c 'DROP TABLE x'",
    "sudo ls",
    "curl -X POST https://x.example -d a",
    "cat .env",
    "cat /etc/hosts",
    "cat ~/.ssh/config",
    "find . -name x -delete",
]

ORDINARY_COMMANDS_STILL_ALLOWED = [
    "git status",
    "git -C . status",
    "git log --oneline -5",
    "git diff origin/main...HEAD",
    "git fetch origin",
    "git checkout -b feat/x origin/main",
    "git commit -m 'feat: a'",
    "git push -u origin feat/backend/x",
    "git push origin HEAD:feat/x",
    "git branch -d merged-branch",
    "git worktree add .worktrees/x -b feat/x origin/main",
    "git stash push -u -m tag",
    "cat .env.example",
    "ls -la docs",
    "grep -rn 'def test_' tests | head",
    "uv run pytest -q -p no:cacheprovider tests/unit",
    "uv run ruff check backend tests",
    "rm docs/old-note.md",
    "sed -n 1,20p CLAUDE.md",
    "cat CLAUDE.md",
    "diff CLAUDE.md docs/x.md",
    'python3 -c "print(1)"',
    "echo hello > .dev/out.txt",
    "ls /tmp/x /dev/null",
    "npm test --prefix frontend",
]


@pytest.fixture(scope="module")
def guard() -> ModuleType:
    """The hardened guard module, loaded from its file."""
    spec = importlib.util.spec_from_file_location("guard_hardened", PATCH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_blocked(guard: ModuleType, command: str) -> bool:
    """True if the guard stops this Bash command (it exits with code 2)."""
    try:
        guard.check_bash(command)
    except SystemExit as stop:
        return stop.code == 2
    return False


@pytest.mark.parametrize("command", BYPASSES_NOW_BLOCKED)
def test_bypass_is_blocked(guard: ModuleType, command: str) -> None:
    """Every variant the old guard let through is stopped."""
    assert _is_blocked(guard, command), command


@pytest.mark.parametrize("command", OLD_BEHAVIOUR_STILL_BLOCKED)
def test_old_protection_is_kept(guard: ModuleType, command: str) -> None:
    """Nothing the old guard blocked is let through now."""
    assert _is_blocked(guard, command), command


@pytest.mark.parametrize("command", ORDINARY_COMMANDS_STILL_ALLOWED)
def test_ordinary_command_is_allowed(guard: ModuleType, command: str) -> None:
    """Normal work is not blocked (including the lower-case safe branch delete)."""
    assert not _is_blocked(guard, command), command


def test_unbalanced_quotes_are_refused(guard: ModuleType) -> None:
    """A command that cannot be parsed is not guessed at."""
    assert _is_blocked(guard, "echo 'unterminated")


def test_github_write_to_main_is_blocked_through_the_hook_entry_point() -> None:
    """The MCP GitHub write tools may not write to main; a feature branch is fine."""

    def run(branch: str) -> int:
        payload = {"tool_name": "mcp__github__push_files", "tool_input": {"branch": branch}}
        result = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [sys.executable, str(PATCH)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        return result.returncode

    assert run("main") == 2
    assert run("refs/heads/master") == 2
    assert run("feat/x") == 0
