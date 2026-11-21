"""Doubles for the startup schema check (BL-8): a scripted SchemaVersionReader."""

from __future__ import annotations


class FakeSchemaReader:
    """Implements ``SchemaVersionReader``; counts reads, can be 'migrated' or made to fail."""

    def __init__(self, current: str | None, expected: str = "0003") -> None:
        self.current = current
        self.expected = expected
        self.fail_with: Exception | None = None
        self.current_calls = 0

    def current_revision(self) -> str | None:
        """The scripted database revision (raises ``fail_with`` when set)."""
        self.current_calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        return self.current

    def expected_revision(self) -> str:
        """The scripted newest shipped revision."""
        return self.expected


def value(state: object) -> object:
    """The plain value of a SchemaState (works for a str-Enum or a plain string)."""
    return getattr(state, "value", state)
