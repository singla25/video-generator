"""Access logs must not record query strings (C5): searches carry names and IDs in the URL."""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

import pytest

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from vidgen.logging import configure_logging


@pytest.fixture
def captured() -> Iterator[io.StringIO]:
    """Configure JSON logging and capture what the root handler would print."""
    stream = io.StringIO()
    configure_logging()
    root = logging.getLogger()
    handler = next(h for h in root.handlers if getattr(h, "_vidgen_handler", False))
    original = handler.stream  # type: ignore[attr-defined]
    handler.stream = stream  # type: ignore[attr-defined]
    yield stream
    handler.stream = original  # type: ignore[attr-defined]


def emit_access(path_with_query: str, status: int = 200) -> None:
    """Emit a record the way uvicorn's access logger does."""
    logger = logging.getLogger("uvicorn.access")
    logger.propagate = True
    logger.setLevel(logging.INFO)
    logger.info(
        '%s - "%s %s HTTP/%s" %d',
        "10.0.0.2:51000",
        "GET",
        path_with_query,
        "1.1",
        status,
    )


def test_query_string_is_removed_from_access_log_lines(captured: io.StringIO) -> None:
    """Only the path is logged."""
    emit_access("/batches/1b2c/rows?search=Rajesh&page=2")
    output = captured.getvalue()
    assert "/batches/1b2c/rows" in output
    assert "search=" not in output
    assert "page=2" not in output
    assert "?" not in output


def test_canary_name_and_id_in_the_query_never_reach_the_log(captured: io.StringIO) -> None:
    """C5: name and ID searches."""
    emit_access(f"/batches/1b2c/rows?search={CANARY_NAME}")
    emit_access(f"/batches/1b2c/rows?search={CANARY_ID}&status=FAILED")
    output = captured.getvalue()
    assert "Canary" not in output
    assert "CANARY1" not in output


def test_percent_encoded_query_values_are_removed_too(captured: io.StringIO) -> None:
    """C5: URL-encoded names (Devanagari, spaces, slashes)."""
    emit_access("/batches/1b2c/rows?search=%E0%A4%B0%E0%A4%BE%E0%A4%9C%20RJ%2F12")
    output = captured.getvalue()
    assert "%E0" not in output
    assert "RJ%2F12" not in output


def test_requests_without_a_query_are_logged_unchanged(captured: io.StringIO) -> None:
    """The filter must not damage normal lines."""
    emit_access("/health", status=200)
    output = captured.getvalue()
    assert "/health" in output
    assert "200" in output
    assert "GET" in output


def test_method_status_and_client_stay_in_the_line(captured: io.StringIO) -> None:
    """Operational value is kept."""
    emit_access("/templates?x=1", status=404)
    output = captured.getvalue()
    assert "404" in output
    assert "GET" in output
    assert "/templates" in output


def test_a_path_that_merely_contains_a_question_mark_character_class_is_safe(
    captured: io.StringIO,
) -> None:
    """Edge: an empty query (`?`) is also cut."""
    emit_access("/templates?")
    assert "?" not in captured.getvalue()


def test_other_loggers_are_not_altered(captured: io.StringIO) -> None:
    """The filter only touches the access logger."""
    logging.getLogger("vidgen.test").info("search is ?a=b")
    assert "?a=b" in captured.getvalue()
