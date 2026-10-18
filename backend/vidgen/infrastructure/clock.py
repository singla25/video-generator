"""System clock adapter for the ``Clock`` port."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Real UTC time."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        return datetime.now(UTC)
