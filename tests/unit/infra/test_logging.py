"""The structured log helper accepts ids and timings only (C5)."""

from __future__ import annotations

import inspect
import json
import logging
import sys
from uuid import uuid4

import pytest

from vidgen.logging import JsonFormatter, log_event

ALLOWED = {
    "logger", "message", "level", "row_id", "row_number", "batch_id", "template_id",
    "stage", "duration_ms", "attempt", "code",
}  # fmt: skip


def test_the_keyword_list_is_closed_and_has_no_room_for_personal_data() -> None:
    """TT-AC17-E11: no name, ID or free-form context parameter exists."""
    assert set(inspect.signature(log_event).parameters) == ALLOWED


@pytest.mark.parametrize("keyword", ["name", "voter_id", "spoken_name", "text", "extra", "context"])
def test_passing_a_name_like_keyword_is_a_type_error(keyword: str) -> None:
    """TT-AC17-E11."""
    logger = logging.getLogger("vidgen.test.helper")
    with pytest.raises(TypeError):
        log_event(logger, "x", **{keyword: "Rajesh"})  # type: ignore[arg-type]


def test_context_ends_up_in_the_json_line() -> None:
    """TT-AC17-P4: the formatter prints the closed context."""
    record = logging.LogRecord("vidgen.test", logging.INFO, __file__, 1, "done", None, None)
    row_id = uuid4()
    record.context = {"stage": "tts", "duration_ms": 12.5, "row_id": str(row_id)}  # type: ignore[attr-defined]
    payload = json.loads(JsonFormatter().format(record))
    assert payload["stage"] == "tts"
    assert payload["row_id"] == str(row_id)
    assert payload["message"] == "done"


def test_exception_text_is_never_printed_only_its_type() -> None:
    """TT-AC17-N4: exception messages may carry names."""
    try:
        raise ValueError("secret Rajesh Kumar")
    except ValueError:
        record = logging.LogRecord(
            "vidgen.test", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )
    line = JsonFormatter().format(record)
    assert "Rajesh" not in line
    assert "ValueError" in line
