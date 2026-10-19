"""Status, analytics, rows list, history, time series (AC14, B6, B7, C1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine

from tests.fixtures.doubles import CANARY_ID
from tests.integration.api.batch_helpers import (
    counts_of,
    finish_row,
    new_batch,
    people,
    running_batch,
    set_batch,
    set_rows,
    status_of,
)
from tests.integration.api.conftest import Env
from vidgen.domain.codes import FailureCode, plain_message

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
NOON = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
DEV_NAME = "\u0930\u093e\u091c\u0947\u0936 \u0915\u0941\u092e\u093e\u0930"
KEYS = {"total", "completed", "processing", "queued", "failed", "skipped", "cancelled"}


# ---- overview counts ------------------------------------------------------------------


def test_overview_has_all_seven_counts_that_add_up_at_every_stage(env: Env, db: Engine) -> None:
    """TT-AC14-P1."""
    rows = [["Asha", "A1"], ["", "B2"], *people(7, prefix="P")]
    batch_id = running_batch(env, rows)
    plan = {
        2: "COMPLETED",
        4: "PROCESSING",
        5: "FAILED",
        6: "CANCELLED",
    }
    for number, status in plan.items():
        set_rows(db, batch_id, [number], status=status)
    counts = counts_of(env, batch_id)
    assert set(counts) == KEYS
    assert counts["total"] == 9
    assert (counts["completed"], counts["processing"], counts["failed"]) == (1, 1, 1)
    assert (counts["cancelled"], counts["skipped"], counts["queued"]) == (1, 1, 4)
    assert sum(v for k, v in counts.items() if k != "total") == counts["total"]


def test_draft_batch_counts_valid_rows_as_queued(env: Env) -> None:
    """TT-AC14-P1."""
    batch_id = new_batch(env, [["Asha", "A1"], ["", "B2"], ["Chand", "C3"]])
    counts = counts_of(env, batch_id)
    assert (counts["total"], counts["queued"], counts["skipped"]) == (3, 2, 1)


def test_batch_where_every_row_is_skipped(env: Env) -> None:
    """TT-AC14-E2."""
    batch_id = new_batch(env, [["", "A1"], ["", "B2"]])
    status = status_of(env, batch_id)
    assert status["counts"]["skipped"] == 2
    assert status["eta_seconds"] is None
    assert status["progress_percent"] == 100.0


def test_progress_is_the_share_of_rows_that_are_no_longer_queued_or_processing(
    env: Env, db: Engine
) -> None:
    """TT-AC14-P2: finished = completed + failed + skipped + cancelled."""
    batch_id = running_batch(env, people(4))
    set_rows(db, batch_id, [2, 3], status="COMPLETED")
    set_rows(db, batch_id, [4], status="FAILED")
    assert status_of(env, batch_id)["progress_percent"] == pytest.approx(75.0)


# ---- ETA (B7, C1) ---------------------------------------------------------------------


def test_eta_is_null_before_the_first_row_completes(env: Env) -> None:
    """TT-AC14-E1, E11 (B7)."""
    batch_id = running_batch(env, people(3))
    assert status_of(env, batch_id)["eta_seconds"] is None


def test_eta_is_remaining_rows_times_the_mean_render_time(env: Env, db: Engine) -> None:
    """TT-AC14-P2 (B7, C1): remaining = QUEUED + PROCESSING."""
    batch_id = running_batch(env, people(6))
    finish_row(db, batch_id, 2, seconds=2.0, at=NOON)
    finish_row(db, batch_id, 3, seconds=4.0, at=NOON + timedelta(seconds=1))
    set_rows(db, batch_id, [4], status="PROCESSING")
    # 3 queued + 1 processing = 4 remaining; mean render time 3 s
    assert status_of(env, batch_id)["eta_seconds"] == pytest.approx(12.0)


def test_eta_uses_only_the_last_twenty_completed_rows(env: Env, db: Engine) -> None:
    """TT-AC14-P2 (B7): the first five slow rows are outside the window."""
    batch_id = running_batch(env, people(30))
    for index in range(25):
        seconds = 100.0 if index < 5 else 2.0
        finish_row(db, batch_id, 2 + index, seconds=seconds, at=NOON + timedelta(seconds=index))
    assert status_of(env, batch_id)["eta_seconds"] == pytest.approx(5 * 2.0)


def test_eta_with_fewer_than_twenty_uses_those_available(env: Env, db: Engine) -> None:
    """TT-AC14-E11."""
    batch_id = running_batch(env, people(3))
    finish_row(db, batch_id, 2, seconds=5.0, at=NOON)
    assert status_of(env, batch_id)["eta_seconds"] == pytest.approx(10.0)


def test_eta_is_zero_when_nothing_remains(env: Env, db: Engine) -> None:
    """TT-AC14-E11."""
    batch_id = running_batch(env, people(1))
    finish_row(db, batch_id, 2, seconds=5.0, at=NOON)
    assert status_of(env, batch_id)["eta_seconds"] == 0.0


# ---- failure breakdown ----------------------------------------------------------------


def test_failure_breakdown_counts_failed_rows_by_code_with_plain_messages(
    env: Env, db: Engine
) -> None:
    """TT-AC14-P3."""
    batch_id = running_batch(env, people(5))
    set_rows(db, batch_id, [2, 3], status="FAILED", failure_code="TTS_FAILED")
    set_rows(db, batch_id, [4], status="FAILED", failure_code="STORAGE_ERROR")
    failures = status_of(env, batch_id)["failures"]
    assert failures == [
        {
            "code": "TTS_FAILED",
            "count": 2,
            "message": plain_message(FailureCode.TTS_FAILED),
        },
        {
            "code": "STORAGE_ERROR",
            "count": 1,
            "message": plain_message(FailureCode.STORAGE_ERROR),
        },
    ]


def test_no_failures_gives_an_empty_breakdown(env: Env) -> None:
    """TT-AC14-E1."""
    assert status_of(env, running_batch(env, people(2)))["failures"] == []


def test_status_of_unknown_batch_is_404(env: Env) -> None:
    """TT-AC14-N2."""
    response = env.client.get(f"/batches/{UNKNOWN_ID}/status")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---- rows list ------------------------------------------------------------------------


def rows_page(env: Env, batch_id: str, **params: object) -> dict[str, object]:
    """GET /batches/{id}/rows with query parameters."""
    response = env.client.get(f"/batches/{batch_id}/rows", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_rows_list_returns_decrypted_name_and_id_for_the_admin(env: Env) -> None:
    """TT-AC14-E9 (B6)."""
    batch_id = new_batch(env, [[DEV_NAME, "RJ/12/097/183866"], ["Asha", "A2"]])
    page = rows_page(env, batch_id)
    first = page["rows"][0]  # type: ignore[index]
    assert first["name"] == DEV_NAME
    assert first["voter_id"] == "RJ/12/097/183866"
    assert first["row_number"] == 2
    assert first["status"] == "QUEUED"


def test_skipped_rows_show_their_code_and_plain_message(env: Env) -> None:
    """TT-AC14-P4."""
    batch_id = new_batch(env, [["", "A1"]])
    row = rows_page(env, batch_id)["rows"][0]  # type: ignore[index]
    assert row["status"] == "SKIPPED"
    assert row["failure_code"] == "INVALID_ROW_EMPTY_NAME"
    assert row["message"] == plain_message(FailureCode.INVALID_ROW_EMPTY_NAME)


def test_rows_are_paged_in_sheet_order(env: Env) -> None:
    """TT-AC14-P4."""
    batch_id = new_batch(env, people(25))
    second = rows_page(env, batch_id, page=2, page_size=10)
    assert [r["row_number"] for r in second["rows"]] == list(range(12, 22))  # type: ignore[attr-defined]
    assert (second["page"], second["page_size"], second["total"], second["total_pages"]) == (
        2,
        10,
        25,
        3,
    )
    last = rows_page(env, batch_id, page=3, page_size=10)
    assert len(last["rows"]) == 5  # type: ignore[arg-type]


def test_status_filter(env: Env, db: Engine) -> None:
    """TT-AC14-P4."""
    batch_id = running_batch(env, people(5))
    set_rows(db, batch_id, [3, 4], status="FAILED", failure_code="TTS_FAILED")
    page = rows_page(env, batch_id, status="FAILED")
    assert [r["row_number"] for r in page["rows"]] == [3, 4]  # type: ignore[attr-defined]
    assert page["total"] == 2


def test_search_by_name_substring_ignores_case_and_works_in_devanagari(env: Env) -> None:
    """TT-AC14-P7 (B6)."""
    batch_id = new_batch(env, [["Asha Verma", "A1"], [DEV_NAME, "A2"], ["Bina", "A3"]])
    assert [r["row_number"] for r in rows_page(env, batch_id, search="VERMA")["rows"]] == [2]  # type: ignore[attr-defined]
    assert [
        r["row_number"]
        for r in rows_page(env, batch_id, search="\u0915\u0941\u092e\u093e\u0930")["rows"]
    ] == [3]  # type: ignore[attr-defined]


def test_search_by_id_including_slashes(env: Env) -> None:
    """TT-AC14-P7, E5 (B6)."""
    batch_id = new_batch(env, [["Asha", "RJ/12/097/183866"], ["Bina", "B2"]])
    found = rows_page(env, batch_id, search="rj/12/097")["rows"]
    assert [r["voter_id"] for r in found] == ["RJ/12/097/183866"]  # type: ignore[attr-defined]


def test_search_with_no_match_is_an_empty_list_not_an_error(env: Env) -> None:
    """TT-AC14-N3."""
    page = rows_page(env, new_batch(env), search="zzzz-nothing")
    assert page["rows"] == []
    assert page["total"] == 0


def test_search_is_limited_to_one_batch(env: Env) -> None:
    """TT-AC14-N3."""
    first = new_batch(env, [["Asha Only", "A1"]])
    second = new_batch(env, [["Bina Other", "B1"]])
    assert rows_page(env, first, search="Bina")["rows"] == []
    assert len(rows_page(env, second, search="Bina")["rows"]) == 1  # type: ignore[arg-type]


def test_search_and_status_filter_combine(env: Env, db: Engine) -> None:
    """TT-AC14-P4."""
    batch_id = running_batch(env, [["Asha One", "A1"], ["Asha Two", "A2"], ["Bina", "B3"]])
    set_rows(db, batch_id, [3], status="FAILED")
    page = rows_page(env, batch_id, search="asha", status="FAILED")
    assert [r["row_number"] for r in page["rows"]] == [3]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "params",
    [{"status": "BOGUS"}, {"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 201}],
)
def test_invalid_paging_or_filter_is_a_validation_error(
    env: Env, params: dict[str, object]
) -> None:
    """TT-AC14-N1."""
    batch_id = new_batch(env)
    response = env.client.get(f"/batches/{batch_id}/rows", params=params)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_error_bodies_never_contain_the_searched_text(env: Env) -> None:
    """TT-AC14-N5 (B6)."""
    batch_id = new_batch(env)
    response = env.client.get(f"/batches/{batch_id}/rows", params={"search": CANARY_ID, "page": 0})
    assert response.status_code == 422
    assert CANARY_ID not in response.text


def test_rows_of_an_unknown_batch_are_404(env: Env) -> None:
    """TT-AC14-N2."""
    assert env.client.get(f"/batches/{UNKNOWN_ID}/rows").status_code == 404


def test_hundred_rows_status_is_one_snapshot_that_adds_up(env: Env, db: Engine) -> None:
    """TT-AC14-E4: every response is self-consistent."""
    batch_id = running_batch(env, people(100))
    set_rows(db, batch_id, list(range(2, 30)), status="COMPLETED")
    counts = counts_of(env, batch_id)
    assert sum(v for k, v in counts.items() if k != "total") == counts["total"] == 100


# ---- history and time series ----------------------------------------------------------


def test_history_lists_batches_newest_first_with_counts_and_success_rate(
    env: Env, db: Engine
) -> None:
    """TT-AC14-P5 (B7): success rate = completed / (completed + failed)."""
    older = running_batch(env, people(4), template_id=None)
    set_rows(db, older, [2, 3, 4], status="COMPLETED")
    set_rows(db, older, [5], status="FAILED")
    env.clock.advance(minutes=5)
    newer = new_batch(env, people(2))
    listing = env.client.get("/batches").json()["batches"]
    assert [b["id"] for b in listing] == [newer, older]
    assert listing[1]["success_rate"] == pytest.approx(0.75)
    assert listing[1]["counts"]["completed"] == 3
    assert listing[0]["success_rate"] is None


def test_success_rate_ignores_skipped_and_cancelled_rows(env: Env, db: Engine) -> None:
    """TT-AC14-P5 (B7)."""
    batch_id = running_batch(env, [["Asha", "A1"], ["", "B2"], ["Chand", "C3"], ["Dev", "D4"]])
    set_rows(db, batch_id, [2], status="COMPLETED")
    set_rows(db, batch_id, [4], status="CANCELLED")
    rate = env.client.get("/batches").json()["batches"][0]["success_rate"]
    assert rate == pytest.approx(1.0)


def test_history_is_paged(env: Env) -> None:
    """TT-AC14-E7."""
    for _ in range(3):
        new_batch(env, people(1))
    page = env.client.get("/batches", params={"page": 2, "page_size": 2}).json()
    assert len(page["batches"]) == 1
    assert (page["total"], page["total_pages"]) == (3, 2)


def test_empty_history_is_an_empty_list(env: Env) -> None:
    """TT-AC14-E7."""
    body = env.client.get("/batches").json()
    assert body["batches"] == []
    assert body["total"] == 0


def test_time_series_counts_videos_per_utc_day_with_mean_render_time(env: Env, db: Engine) -> None:
    """TT-AC14-P6, E10 (B7): UTC days; zero days are included."""
    batch_id = running_batch(env, people(5))
    finish_row(db, batch_id, 2, seconds=2.0, at=datetime(2026, 10, 18, 23, 59, 59, tzinfo=UTC))
    finish_row(db, batch_id, 3, seconds=4.0, at=datetime(2026, 10, 19, 0, 0, 1, tzinfo=UTC))
    finish_row(db, batch_id, 4, seconds=6.0, at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
    env.advance(days=2)  # now: 2026-10-20 09:00 UTC
    days = env.client.get("/stats/daily", params={"days": 4}).json()["days"]
    assert [d["date"] for d in days] == ["2026-10-17", "2026-10-18", "2026-10-19", "2026-10-20"]
    by_date = {d["date"]: d for d in days}
    assert by_date["2026-10-17"] == {"date": "2026-10-17", "videos": 0, "avg_render_seconds": None}
    assert by_date["2026-10-18"]["videos"] == 1
    assert by_date["2026-10-18"]["avg_render_seconds"] == pytest.approx(2.0)
    assert by_date["2026-10-19"]["videos"] == 2
    assert by_date["2026-10-19"]["avg_render_seconds"] == pytest.approx(5.0)


def test_time_series_counts_only_completed_rows(env: Env, db: Engine) -> None:
    """TT-AC14-P6, P8: failed, queued and preview renders are excluded."""
    batch_id = running_batch(env, people(3))
    finish_row(db, batch_id, 2, seconds=2.0, at=NOON)
    set_rows(db, batch_id, [3], status="FAILED", finished_at=NOON)
    days = env.client.get("/stats/daily", params={"days": 1}).json()["days"]
    assert days[0]["videos"] == 1


@pytest.mark.parametrize("days", [0, -1, 400])
def test_time_series_rejects_unreasonable_ranges(env: Env, days: int) -> None:
    """TT-AC14-N1."""
    response = env.client.get("/stats/daily", params={"days": days})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_time_series_default_covers_thirty_days(env: Env) -> None:
    """TT-AC14-P6."""
    assert len(env.client.get("/stats/daily").json()["days"]) == 30


def test_batch_finish_time_is_returned_when_set(env: Env, db: Engine) -> None:
    """TT-AC14-P5."""
    batch_id = running_batch(env, people(1))
    set_batch(db, batch_id, status="COMPLETED", finished_at=NOON)
    body = env.client.get(f"/batches/{batch_id}").json()
    assert body["status"] == "COMPLETED"
    assert body["finished_at"].startswith("2026-10-18T12:00:00")
