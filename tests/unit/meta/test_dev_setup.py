"""scripts/dev_setup.py: the pending-migration listing dev_up.sh uses before asking y/N."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

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
