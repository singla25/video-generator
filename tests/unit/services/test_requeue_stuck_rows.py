"""L10(d): recover rows whose queue message was lost (Redis flush/restart). No migration.

EXPECTED API (see docs/test-tree/m2-local-real-ai.md)
  vidgen.ports.batches:
    StuckRow(batch_id: UUID, row_id: UUID, kind: Literal["row", "preview"])   frozen dataclass
    BatchStore.stuck_candidates(cutoff, after: UUID | None, limit: int) -> list[StuckRow]
        QUEUED rows of RUNNING batches started before cutoff, plus the preview row of DRAFT
        batches with preview PENDING; ordered by row_id; keyset page (row_id > after).
    JobQueue.has_live_job(row_id: UUID) -> bool   True while a message for the row is queued/running
  vidgen.services.requeue.requeue_stuck_rows(open_uow, queue, clock, *, stuck_after_seconds=600,
        page_size=500) -> RequeueReport(requeued: int, skipped_live: int, queue_down: bool)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.fixtures.doubles import FakeClock
from vidgen.ports.batches import StuckRow
from vidgen.services.requeue import RequeueReport, requeue_stuck_rows

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


class Store:
    """BatchStore double: candidates are pre-filtered like the SQL query would."""

    def __init__(self, rows: list[StuckRow]) -> None:
        self.rows = sorted(rows, key=lambda r: r.row_id)
        self.calls: list[tuple[datetime, UUID | None, int]] = []
        self.largest_page = 0

    def stuck_candidates(self, cutoff: datetime, after: UUID | None, limit: int) -> list[StuckRow]:
        self.calls.append((cutoff, after, limit))
        page = [r for r in self.rows if after is None or r.row_id > after][:limit]
        self.largest_page = max(self.largest_page, len(page))
        return page


class Queue:
    """JobQueue double that knows which rows have a live job."""

    def __init__(self, live: set[UUID] | None = None, *, down: bool = False) -> None:
        self.live = set(live or ())
        self.down = down
        self.rows: list[tuple[UUID, UUID]] = []
        self.previews: list[tuple[UUID, UUID]] = []

    def has_live_job(self, row_id: UUID) -> bool:
        if self.down:
            raise ConnectionError("redis down")
        return row_id in self.live

    def enqueue_rows(self, batch_id: UUID, row_ids: list[UUID]) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.rows.extend((batch_id, r) for r in row_ids)
        self.live.update(row_ids)

    def enqueue_preview(self, batch_id: UUID, row_id: UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.previews.append((batch_id, row_id))
        self.live.add(row_id)

    def depth(self) -> int:
        return len(self.rows) + len(self.previews)


def uow_for(store: Store) -> Any:
    """``open_uow`` returning a context manager with ``.batches``."""

    class Uow:
        batches = store

        def __enter__(self) -> Uow:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    return lambda: Uow()


def stuck(batch: UUID, kind: str = "row") -> StuckRow:
    return StuckRow(batch_id=batch, row_id=uuid4(), kind=kind)  # type: ignore[arg-type]


def run(store: Store, queue: Queue, **kw: Any) -> RequeueReport:
    clock = FakeClock(NOW)
    return requeue_stuck_rows(uow_for(store), queue, clock, **kw)


# ---- positive ---------------------------------------------------------------------------


def test_stuck_rows_without_a_live_job_are_requeued_once_each() -> None:
    batch = uuid4()
    rows = [stuck(batch) for _ in range(3)]
    queue = Queue()
    report = run(Store(rows), queue)
    assert sorted(r for _, r in queue.rows) == sorted(r.row_id for r in rows)
    assert report == RequeueReport(requeued=3, skipped_live=0, queue_down=False)


def test_rows_are_grouped_per_batch_in_one_enqueue_call_each() -> None:
    a, b = uuid4(), uuid4()
    rows = [stuck(a), stuck(b), stuck(a)]
    queue = Queue()
    run(Store(rows), queue)
    assert {batch for batch, _ in queue.rows} == {a, b}
    assert len(queue.rows) == 3


def test_a_pending_preview_is_requeued_as_a_preview_job() -> None:
    row = stuck(uuid4(), "preview")
    queue = Queue()
    run(Store([row]), queue)
    assert queue.previews == [(row.batch_id, row.row_id)]
    assert queue.rows == []


def test_the_cutoff_is_now_minus_stuck_after_seconds() -> None:
    store = Store([])
    run(store, Queue(), stuck_after_seconds=900)
    assert store.calls[0][0] == NOW - timedelta(seconds=900)


def test_default_stuck_after_is_ten_minutes() -> None:
    store = Store([])
    run(store, Queue())
    assert store.calls[0][0] == NOW - timedelta(seconds=600)


# ---- negative / safety ------------------------------------------------------------------


def test_rows_with_a_live_job_are_left_alone() -> None:
    rows = [stuck(uuid4()), stuck(uuid4())]
    queue = Queue(live={rows[0].row_id})
    report = run(Store(rows), queue)
    assert [r for _, r in queue.rows] == [rows[1].row_id]
    assert report.skipped_live == 1
    assert report.requeued == 1


def test_a_second_run_creates_no_duplicates() -> None:
    store, queue = Store([stuck(uuid4()) for _ in range(5)]), Queue()
    run(store, queue)
    again = run(store, queue)
    assert len(queue.rows) == 5
    assert again.requeued == 0
    assert again.skipped_live == 5


def test_empty_database_returns_an_empty_report() -> None:
    assert run(Store([]), Queue()) == RequeueReport(requeued=0, skipped_live=0, queue_down=False)


def test_queue_down_is_logged_and_returns_without_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    report = run(Store([stuck(uuid4())]), Queue(down=True))
    assert report.queue_down is True
    assert report.requeued == 0
    assert any("queue" in r.getMessage().lower() for r in caplog.records)


def test_queue_failing_midway_keeps_what_was_requeued_and_does_not_raise() -> None:
    class Flaky(Queue):
        def enqueue_rows(self, batch_id: UUID, row_ids: list[UUID]) -> None:
            if self.rows:
                raise ConnectionError("lost")
            super().enqueue_rows(batch_id, row_ids)

    batches = [uuid4() for _ in range(3)]
    queue = Flaky()
    report = run(Store([stuck(b) for b in batches]), queue)
    assert report.queue_down is True
    assert report.requeued == len(queue.rows)


def test_row_ids_are_not_logged_with_names_only_counts(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    run(Store([stuck(uuid4())]), Queue())
    assert "name" not in caplog.text.lower()


# ---- paging -----------------------------------------------------------------------------


def test_ten_thousand_rows_are_read_in_pages_never_all_at_once() -> None:
    batch = uuid4()
    store = Store([stuck(batch) for _ in range(10_000)])
    queue = Queue()
    report = run(store, queue, page_size=500)
    assert report.requeued == 10_000
    assert len(queue.rows) == 10_000
    assert store.largest_page <= 500
    assert len(store.calls) >= 20
    assert all(limit == 500 for _, _, limit in store.calls)


def test_paging_continues_from_the_last_row_id() -> None:
    store = Store([stuck(uuid4()) for _ in range(5)])
    run(store, Queue(), page_size=2)
    afters = [after for _, after, _ in store.calls]
    assert afters[0] is None
    assert afters[1] == store.rows[1].row_id
    assert afters[2] == store.rows[3].row_id


def test_page_size_must_be_positive() -> None:
    with pytest.raises(ValueError):
        run(Store([]), Queue(), page_size=0)
