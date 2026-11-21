"""Read-only adapter for the schema revision: the stored one and the newest shipped one.

It only reads. Applying migrations stays a manual Admin step; the app never does it.
"""

from __future__ import annotations

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

VERSION_TABLE = "alembic_version"
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


class SqlSchemaVersionReader:
    """Implements ``SchemaVersionReader`` on a SQLAlchemy engine."""

    def __init__(self, engine: Engine, migrations_dir: Path = MIGRATIONS_DIR) -> None:
        self._engine = engine
        self._migrations_dir = migrations_dir
        self._expected: str | None = None

    def current_revision(self) -> str | None:
        """The stored revision; None for a missing table or an empty one. Errors propagate."""
        with self._engine.connect() as conn:
            if not inspect(conn).has_table(VERSION_TABLE):
                return None
            row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
        return None if row is None else str(row[0])

    def expected_revision(self) -> str:
        """The head of the shipped migration scripts (cached: the scripts do not change)."""
        if self._expected is None:
            head = ScriptDirectory(str(self._migrations_dir)).get_current_head()
            if head is None:
                raise RuntimeError("no migration scripts found")
            self._expected = head
        return self._expected
