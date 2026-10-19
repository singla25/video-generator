"""POST /batches/inspect-sheet: read headers and a sample without creating anything (DD-16 a).

Contract: multipart ``sheet`` -> 200 {sheet_name, headers[], sample_rows (first 5), row_count}.
Headers are trimmed and a BOM is stripped. It stores no file and creates no batch. Unsupported or
empty sheets give 422 UNSUPPORTED_SHEET; over ``max_sheet_bytes`` gives 413 UNSUPPORTED_SHEET.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from httpx import Response
from sqlalchemy import Engine

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from tests.integration.api.batch_helpers import (
    csv_bytes,
    people,
    table_count,
    xlsx_bytes,
)
from tests.integration.api.conftest import Env, EnvFactory
from vidgen.infrastructure.db.models import Batch, BatchRow

DEVANAGARI = "राजेश कुमार"
URL = "/batches/inspect-sheet"


def inspect(
    env: Env, content: bytes, filename: str = "sheet.csv", *, headers: dict[str, str] | None = None
) -> Response:
    """POST the sheet to inspect-sheet with the CSRF header unless ``headers`` is given."""
    return env.client.post(
        URL,
        files={"sheet": (filename, content, "application/octet-stream")},
        headers=env.csrf if headers is None else headers,
    )


def test_csv_returns_headers_sample_and_row_count(env: Env) -> None:
    """Happy path, CSV: 8 data rows, only the first 5 as sample text."""
    response = inspect(env, csv_bytes([["Name", "ID"], *people(8)]))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert set(body) == {"sheet_name", "headers", "sample_rows", "row_count"}
    assert body["headers"] == ["Name", "ID"]
    assert body["row_count"] == 8
    assert body["sample_rows"] == [
        ["Person A", "ID1"],
        ["Person B", "ID2"],
        ["Person C", "ID3"],
        ["Person D", "ID4"],
        ["Person E", "ID5"],
    ]
    assert isinstance(body["sheet_name"], str)


def test_xlsx_returns_first_sheet_name_and_values_as_text(env: Env) -> None:
    """Happy path, xlsx: first worksheet only; numbers come back as text."""
    content = xlsx_bytes(
        {"Voters": [["Name", "ID"], ["Asha", 12345], [DEVANAGARI, 7]], "Other": [["X"], ["y"]]}
    )
    body = inspect(env, content, "s.xlsx").json()
    assert body["sheet_name"] == "Voters"
    assert body["headers"] == ["Name", "ID"]
    assert body["sample_rows"] == [["Asha", "12345"], [DEVANAGARI, "7"]]
    assert body["row_count"] == 2


def test_headers_are_trimmed(env: Env) -> None:
    """Header normalisation: surrounding spaces removed, case kept for display."""
    body = inspect(env, csv_bytes([["  Voter Name ", " ID\t"], ["A", "1"]])).json()
    assert body["headers"] == ["Voter Name", "ID"]


def test_utf8_bom_is_stripped_from_the_first_header(env: Env) -> None:
    """A BOM must not leak into the first column name."""
    body = inspect(env, csv_bytes([["Name", "ID"], ["A", "1"]], bom=True)).json()
    assert body["headers"][0] == "Name"


def test_semicolon_delimited_csv_is_split_like_the_batch_upload(env: Env) -> None:
    """Same parser as batch creation."""
    body = inspect(env, csv_bytes([["Name", "ID"], ["A", "1"]], delimiter=";")).json()
    assert body["headers"] == ["Name", "ID"]


def test_short_sheet_returns_all_rows_in_the_sample(env: Env) -> None:
    """Fewer than five rows: the sample holds them all."""
    body = inspect(env, csv_bytes([["Name", "ID"], *people(2)])).json()
    assert len(body["sample_rows"]) == 2
    assert body["row_count"] == 2


@pytest.mark.parametrize("filename", ["s.xls", "s.txt", "s.ods", "s"])
def test_unsupported_file_types_are_refused(env: Env, filename: str) -> None:
    """Wrong extension: 422 UNSUPPORTED_SHEET."""
    response = inspect(env, csv_bytes([["Name", "ID"], *people(2)]), filename)
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"", "s.csv"),
        (b"PK\x03\x04 not really", "s.xlsx"),
        (csv_bytes([["Name", "ID"]]), "s.csv"),
    ],
    ids=["empty-file", "corrupt-xlsx", "headers-only"],
)
def test_empty_or_corrupt_sheets_are_refused(env: Env, content: bytes, filename: str) -> None:
    """Empty, corrupt and header-only sheets: 422 UNSUPPORTED_SHEET."""
    response = inspect(env, content, filename)
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"


def test_missing_sheet_field_is_a_validation_error(env: Env) -> None:
    """No file part at all."""
    response = env.client.post(URL, data={"x": "y"}, headers=env.csrf)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_oversize_sheet_is_413(make_env: EnvFactory) -> None:
    """Byte limit enforced while streaming, same as batch creation."""
    env = make_env(max_sheet_bytes=2048)
    response = inspect(env, csv_bytes([["Name", "ID"], *people(500)]))
    assert response.status_code == 413
    assert response.json()["code"] == "UNSUPPORTED_SHEET"


def test_login_is_required(anon: Env) -> None:
    """No session: 401 UNAUTHENTICATED."""
    response = inspect(anon, csv_bytes([["Name", "ID"], *people(1)]), headers={})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_csrf_header_is_required(env: Env) -> None:
    """Logged in but no X-CSRF-Token: 403 CSRF_FAILED."""
    response = inspect(env, csv_bytes([["Name", "ID"], *people(1)]), headers={})
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"


def test_inspecting_persists_nothing(env: Env, db: Engine) -> None:
    """No batch, no row, no stored file."""
    stored_before = dict(env.storage.files)
    assert inspect(env, csv_bytes([["Name", "ID"], *people(5)])).status_code == 200
    assert table_count(db, Batch) == 0
    assert table_count(db, BatchRow) == 0
    assert env.storage.files == stored_before


def test_failed_inspection_persists_nothing_either(env: Env, db: Engine) -> None:
    """A refused sheet leaves no trace."""
    stored_before = dict(env.storage.files)
    assert inspect(env, b"", "s.csv").status_code == 422
    assert table_count(db, Batch) == 0
    assert env.storage.files == stored_before


def test_names_and_ids_stay_out_of_the_logs_and_errors(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    """Canary name and ID never appear in log output (privacy B6), also on errors."""
    good = csv_bytes([["Name", "ID"], [CANARY_NAME, CANARY_ID]])
    bad = csv_bytes([["Name", "ID"], [CANARY_NAME, CANARY_ID]])
    with caplog.at_level(logging.DEBUG):
        assert inspect(env, good).status_code == 200
        error = inspect(env, bad, "s.xls")
    assert error.status_code == 422
    assert CANARY_NAME not in caplog.text
    assert CANARY_ID not in caplog.text
    assert CANARY_NAME not in error.text
