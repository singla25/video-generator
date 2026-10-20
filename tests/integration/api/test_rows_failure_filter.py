"""GET /batches/{id}/rows?failure_code=CODE filter (DD-16 b).

Combines with status, search and paging. An unknown code is 422 VALIDATION_ERROR.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from tests.integration.api.batch_helpers import (
    approve_preview,
    new_batch,
    people,
    running_batch,
    set_rows,
    start,
)
from tests.integration.api.conftest import Env


def numbers(env: Env, batch_id: str, **params: object) -> list[int]:
    """Row numbers returned by GET rows with ``params``."""
    response = env.client.get(f"/batches/{batch_id}/rows", params=params)
    assert response.status_code == 200, response.text
    return [r["row_number"] for r in response.json()["rows"]]


@pytest.fixture
def failed_batch(env: Env, db: Engine) -> str:
    """Eight rows: 3,4 TTS_FAILED; 5 STORAGE_ERROR; 6 skipped; the rest queued."""
    batch_id = running_batch(env, people(8))
    set_rows(db, batch_id, [3, 4], status="FAILED", failure_code="TTS_FAILED")
    set_rows(db, batch_id, [5], status="FAILED", failure_code="STORAGE_ERROR")
    set_rows(db, batch_id, [6], status="SKIPPED", failure_code="INVALID_ROW_EMPTY_NAME")
    return batch_id


def test_filter_returns_only_rows_with_that_code(env: Env, failed_batch: str) -> None:
    """Correct subset, correct total."""
    response = env.client.get(
        f"/batches/{failed_batch}/rows", params={"failure_code": "TTS_FAILED"}
    )
    assert response.status_code == 200
    body = response.json()
    assert [r["row_number"] for r in body["rows"]] == [3, 4]
    assert body["total"] == 2
    assert all(r["failure_code"] == "TTS_FAILED" for r in body["rows"])


def test_filter_works_for_skipped_row_codes(env: Env, failed_batch: str) -> None:
    """Validation codes on skipped rows are filterable too."""
    assert numbers(env, failed_batch, failure_code="INVALID_ROW_EMPTY_NAME") == [6]


def test_known_code_with_no_rows_is_an_empty_page(env: Env, failed_batch: str) -> None:
    """Not an error."""
    response = env.client.get(
        f"/batches/{failed_batch}/rows", params={"failure_code": "STT_FAILED"}
    )
    assert response.status_code == 200
    assert response.json()["rows"] == []
    assert response.json()["total"] == 0


def test_without_the_parameter_nothing_changes(env: Env, failed_batch: str) -> None:
    """All eight rows."""
    assert numbers(env, failed_batch) == list(range(2, 10))


def test_combines_with_status(env: Env, failed_batch: str) -> None:
    """Matching status keeps rows, a different status removes them."""
    assert numbers(env, failed_batch, failure_code="TTS_FAILED", status="FAILED") == [3, 4]
    assert numbers(env, failed_batch, failure_code="TTS_FAILED", status="SKIPPED") == []


def test_combines_with_search(env: Env, failed_batch: str) -> None:
    """Search narrows within the code: row 4 is 'Person C'; row 5 ('Person D') has another code."""
    assert numbers(env, failed_batch, failure_code="TTS_FAILED", search="person c") == [4]
    assert numbers(env, failed_batch, failure_code="TTS_FAILED", search="person d") == []


def test_paging_counts_only_the_filtered_rows(env: Env, db: Engine) -> None:
    """25 failed rows, page size 10: totals and pages are for the filtered set."""
    batch_id = running_batch(env, people(30))
    set_rows(db, batch_id, list(range(2, 27)), status="FAILED", failure_code="RENDER_TIMEOUT")
    set_rows(db, batch_id, [27, 28], status="FAILED", failure_code="TTS_FAILED")
    page3 = env.client.get(
        f"/batches/{batch_id}/rows",
        params={"failure_code": "RENDER_TIMEOUT", "page": 3, "page_size": 10},
    ).json()
    assert [r["row_number"] for r in page3["rows"]] == [22, 23, 24, 25, 26]
    assert (page3["total"], page3["total_pages"]) == (25, 3)


@pytest.mark.parametrize("code", ["BOGUS", "tts_failed", "", "TTS_FAILED; DROP TABLE", "x" * 300])
def test_unknown_code_is_a_validation_error(env: Env, failed_batch: str, code: str) -> None:
    """Only real FailureCode values are accepted (case-sensitive)."""
    response = env.client.get(f"/batches/{failed_batch}/rows", params={"failure_code": code})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_filter_is_limited_to_one_batch(env: Env, db: Engine, failed_batch: str) -> None:
    """Another batch with the same code does not leak in."""
    other = new_batch(env, people(3))
    approve_preview(env, other)
    assert start(env, other, key="key-2").status_code == 200
    set_rows(db, other, [2], status="FAILED", failure_code="TTS_FAILED")
    assert numbers(env, failed_batch, failure_code="TTS_FAILED") == [3, 4]
    assert numbers(env, other, failure_code="TTS_FAILED") == [2]
