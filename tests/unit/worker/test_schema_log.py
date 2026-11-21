"""BL-8 SS-W*: the worker logs one ERROR at start when the database is behind, and still starts.

CONTRACT (assumed): ``vidgen.worker.schema_log.report_schema_at_start(check) -> SchemaStatus``;
the worker's ``run()`` calls it once before it starts consuming. It never migrates and never
raises because of the schema state.
"""

from __future__ import annotations

import logging

import pytest

from tests.fixtures.doubles import FakeClock
from tests.fixtures.schema_doubles import FakeSchemaReader, value
from vidgen.services.schema_check import SchemaCheck
from vidgen.worker.schema_log import report_schema_at_start

MESSAGE = "The database needs migration 0003 (it is at 0002). Ask the admin to run it."


def check_for(current: str | None) -> SchemaCheck:
    return SchemaCheck(FakeSchemaReader(current), FakeClock(), 5)


@pytest.mark.parametrize("current", ["0002", None])
def test_behind_logs_one_error_with_the_message(
    current: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """SS-W-P1."""
    with caplog.at_level(logging.INFO):
        status = report_schema_at_start(check_for(current))
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert status.message in errors[0].getMessage()
    assert value(status.state) in ("behind", "empty")


def test_error_text_is_the_exact_sentence(caplog: pytest.LogCaptureFixture) -> None:
    """SS-W-P2."""
    with caplog.at_level(logging.ERROR):
        report_schema_at_start(check_for("0002"))
    assert MESSAGE in caplog.text


@pytest.mark.parametrize("current", ["0003", "0004"])
def test_ok_and_ahead_log_no_error(current: str, caplog: pytest.LogCaptureFixture) -> None:
    """SS-W-N1: nothing to report; the worker starts quietly."""
    with caplog.at_level(logging.INFO):
        report_schema_at_start(check_for(current))
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_behind_does_not_stop_the_worker_and_never_migrates() -> None:
    """SS-W-E1: returns normally (the worker still starts); the reader is only read."""
    reader = FakeSchemaReader("0002")
    report_schema_at_start(SchemaCheck(reader, FakeClock(), 5))
    assert reader.current == "0002"
    assert reader.current_calls == 1
