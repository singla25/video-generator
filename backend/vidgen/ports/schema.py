"""Port: read the database schema revision (read-only)."""

from __future__ import annotations

from typing import Protocol


class SchemaVersionReader(Protocol):
    """Reads which migration the database is at and which one the code ships."""

    def current_revision(self) -> str | None:
        """The revision stored in the database, or None when there is none."""
        ...

    def expected_revision(self) -> str:
        """The newest revision shipped with this version of the app."""
        ...
