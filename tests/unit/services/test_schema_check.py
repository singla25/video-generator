"""BL-8 SS-S*: SchemaCheck(reader, clock, ttl_seconds).status() with a cache and a fake clock."""

from __future__ import annotations

import contextlib

import pytest
from sqlalchemy.exc import OperationalError

from tests.fixtures.doubles import FakeClock
from tests.fixtures.schema_doubles import FakeSchemaReader, value
from vidgen.services.schema_check import SchemaCheck

TTL = 5


def make(
    current: str | None, expected: str = "0003"
) -> tuple[SchemaCheck, FakeSchemaReader, FakeClock]:
    reader, clock = FakeSchemaReader(current, expected), FakeClock()
    return SchemaCheck(reader, clock, TTL), reader, clock


def test_ok_status_has_no_block_message() -> None:
    """SS-S-P1: database at the expected revision -> state ok, current and expected filled."""
    check, _, _ = make("0003")
    status = check.status()
    assert value(status.state) == "ok"
    assert (status.current, status.expected) == ("0003", "0003")


def test_behind_message_is_exact() -> None:
    """SS-S-P2: the Admin-facing text is exactly the agreed sentence."""
    status = make("0002")[0].status()
    assert value(status.state) == "behind"
    assert status.message == (
        "The database needs migration 0003 (it is at 0002). Ask the admin to run it."
    )


def test_empty_message_says_none() -> None:
    """SS-S-P3: no alembic_version row -> 'it is at none'."""
    status = make(None)[0].status()
    assert value(status.state) == "empty"
    assert status.current is None
    assert status.message == (
        "The database needs migration 0003 (it is at none). Ask the admin to run it."
    )


def test_ahead_message_and_state() -> None:
    """SS-S-P4: a newer database is reported but its message is the 'newer' sentence."""
    status = make("0004")[0].status()
    assert value(status.state) == "ahead"
    assert status.message == "The database is newer than this version of the app."


def test_unknown_current_is_behind_and_keeps_the_raw_value() -> None:
    """SS-S-E1: a non-numeric revision is behind and the raw text is kept."""
    status = make("weird-rev")[0].status()
    assert value(status.state) == "behind"
    assert status.current == "weird-rev"
    assert "weird-rev" in status.message


def test_second_call_inside_ttl_does_not_hit_the_reader() -> None:
    """SS-S-P5: cached for the TTL so the database is not read on every request."""
    check, reader, clock = make("0002")
    check.status()
    clock.advance(seconds=TTL - 1)
    check.status()
    assert reader.current_calls == 1


def test_after_the_ttl_the_reader_is_asked_again() -> None:
    """SS-S-P6: after the Admin migrates, the next call after the TTL sees ok (no restart)."""
    check, reader, clock = make("0002")
    assert value(check.status().state) == "behind"
    reader.current = "0003"  # the Admin ran the migration
    clock.advance(seconds=TTL - 1)
    assert value(check.status().state) == "behind"  # still cached
    clock.advance(seconds=2)
    assert value(check.status().state) == "ok"
    assert reader.current_calls == 2


def test_reader_database_error_is_not_cached() -> None:
    """SS-S-N2: when the database is down the failure is not remembered as a status.

    Either outcome of the first call is accepted (the existing DB-unavailable handling takes
    over at the API); the next call, with the database back, must be right without waiting.
    """
    check, reader, _ = make("0003")
    reader.fail_with = OperationalError("SELECT 1", {}, Exception("down"))
    with contextlib.suppress(OperationalError):
        check.status()
    reader.fail_with = None
    assert value(check.status().state) == "ok"


@pytest.mark.parametrize("ttl", [0, -1])
def test_non_positive_ttl_is_rejected(ttl: int) -> None:
    """SS-S-E2: a TTL below one second is a programming error, not 'never cache'."""
    with pytest.raises(ValueError):
        SchemaCheck(FakeSchemaReader("0003"), FakeClock(), ttl)
