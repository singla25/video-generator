"""Cached check of the database schema against the code (BL-8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from vidgen.domain.schema_state import SchemaState, classify
from vidgen.ports import Clock
from vidgen.ports.schema import SchemaVersionReader

NEEDS_MIGRATION_TEXT = (
    "The database needs migration {expected} (it is at {current}). Ask the admin to run it."
)
AHEAD_TEXT = "The database is newer than this version of the app."


@dataclass(frozen=True)
class SchemaStatus:
    """Result of one check; ``message`` is empty when the state is ok."""

    state: SchemaState
    current: str | None
    expected: str
    message: str

    @property
    def blocks(self) -> bool:
        """True when the data routes must refuse work (behind or empty)."""
        return self.state in (SchemaState.BEHIND, SchemaState.EMPTY)


def _message(state: SchemaState, current: str | None, expected: str) -> str:
    if state is SchemaState.AHEAD:
        return AHEAD_TEXT
    if state is SchemaState.OK:
        return ""
    return NEEDS_MIGRATION_TEXT.format(expected=expected, current=current or "none")


class SchemaCheck:
    """Asks the reader at most once per TTL; reader errors propagate and are never cached."""

    def __init__(self, reader: SchemaVersionReader, clock: Clock, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be at least 1")
        self._reader, self._clock = reader, clock
        self._ttl = timedelta(seconds=ttl_seconds)
        self._cached: tuple[datetime, SchemaStatus] | None = None

    def status(self) -> SchemaStatus:
        """The current status, from cache while it is fresh."""
        now = self._clock.now()
        if self._cached is not None and now - self._cached[0] < self._ttl:
            return self._cached[1]
        current, expected = self._reader.current_revision(), self._reader.expected_revision()
        state = classify(current, expected)
        status = SchemaStatus(state, current, expected, _message(state, current, expected))
        self._cached = (now, status)
        return status
