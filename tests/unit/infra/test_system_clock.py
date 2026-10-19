"""The real clock adapter returns aware UTC time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from vidgen.infrastructure.clock import SystemClock


def test_now_is_timezone_aware_and_in_utc() -> None:
    """The Clock port promises an aware UTC datetime."""
    value = SystemClock().now()
    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


def test_now_is_close_to_the_system_time_and_does_not_go_backwards() -> None:
    """Two readings are ordered and within a few seconds of the real time."""
    clock = SystemClock()
    first = clock.now()
    second = clock.now()
    assert second >= first
    assert abs(datetime.now(UTC) - second) < timedelta(seconds=5)
