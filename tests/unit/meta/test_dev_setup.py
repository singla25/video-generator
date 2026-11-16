"""scripts/dev_setup.py: the pending-migration listing dev_up.sh uses before asking y/N."""

from __future__ import annotations

import getpass
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest
from argon2 import PasswordHasher
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]


def load_dev_setup() -> ModuleType:
    """Import scripts/dev_setup.py (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("dev_setup", ROOT / "scripts" / "dev_setup.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_database_lists_every_migration_oldest_first(tmp_path: Path) -> None:
    """A database with no alembic_version has all migrations pending, in apply order."""
    dev = load_dev_setup()
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    pending = dev.pending_migrations(url)
    assert pending, "the project has migrations, so a fresh database has pending ones"
    assert all(len(rev) > 0 and isinstance(msg, str) for rev, msg in pending)
    assert [rev for rev, _ in pending][-1] == dev.head_revision()


def test_database_at_head_has_nothing_pending(tmp_path: Path) -> None:
    """When alembic_version already holds the head revision, nothing is pending."""
    dev = load_dev_setup()
    url = f"sqlite:///{tmp_path / 'head.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("create table alembic_version (version_num varchar(32) not null)"))
        conn.execute(text("insert into alembic_version values (:v)"), {"v": dev.head_revision()})
    assert dev.pending_migrations(url) == []


def test_pending_listing_never_changes_the_database(tmp_path: Path) -> None:
    """Looking must not apply anything (no tables are created)."""
    dev = load_dev_setup()
    path = tmp_path / "look.db"
    dev.pending_migrations(f"sqlite:///{path}")
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        tables = conn.execute(text("select name from sqlite_master")).fetchall()
    assert tables == []


# --- hash-password: hashing for the installer (password on stdin, hash on stdout) -------------

DEMO_PASSWORD = "DemoPass-123"  # noqa: S105


def run_hash_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stdin_text: str,
) -> tuple[int, str, str]:
    """Run ``dev_setup.py hash-password`` in-process with ``stdin_text`` on stdin."""
    dev = load_dev_setup()
    monkeypatch.setattr(sys, "argv", ["dev_setup.py", "hash-password"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))

    def no_tty(prompt: str = "") -> str:
        raise AssertionError("hash-password must read stdin, not the terminal")

    monkeypatch.setattr(getpass, "getpass", no_tty)
    code = dev.main()
    seen = capsys.readouterr()
    return code, seen.out, seen.err


def test_hash_password_prints_only_a_verifiable_argon2_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _err = run_hash_password(monkeypatch, capsys, DEMO_PASSWORD + "\n")
    assert code == 0
    hashed = out.strip()
    assert out.count("\n") == 1 and hashed.startswith("$argon2")
    assert PasswordHasher().verify(hashed, DEMO_PASSWORD)


def test_hash_password_never_echoes_the_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _code, out, err = run_hash_password(monkeypatch, capsys, DEMO_PASSWORD + "\n")
    assert DEMO_PASSWORD not in out + err


@pytest.mark.parametrize("stdin_text", ["short\n", "elevenchars\n", "x" * 11])
def test_hash_password_rejects_a_password_under_12_chars(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin_text: str
) -> None:
    code, out, err = run_hash_password(monkeypatch, capsys, stdin_text)
    assert code != 0 and out == ""
    assert "12" in err and stdin_text.strip() not in err


@pytest.mark.parametrize("stdin_text", ["", "\n", "   \n"])
def test_hash_password_rejects_empty_stdin_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin_text: str
) -> None:
    code, out, err = run_hash_password(monkeypatch, capsys, stdin_text)
    assert code != 0 and out == ""
    assert "password" in err.lower()


def test_hash_password_keeps_unicode_and_inner_spaces(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    password = "pässwörd 日本語 🎬 ok"  # noqa: S105
    code, out, _err = run_hash_password(monkeypatch, capsys, password + "\n")
    assert code == 0
    assert PasswordHasher().verify(out.strip(), password)
