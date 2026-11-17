"""RP-RTE: requeue of stuck rows goes to the batch provider's queue (AC6).

EXPECTED API
  vidgen.ports.batches.StuckRow gains ``provider_id: str | None = None`` (last field, defaulted)
  requeue_stuck_rows(..., provider_queues: Mapping[str, str] | None = None)
      provider_queues maps provider id -> queue name. A row of a batch whose provider id is in the
      map is enqueued with ``queue_name=<queue>``; null or unmapped provider -> the call is made
      WITHOUT a queue_name (legacy call shape, default queue).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from tests.fixtures.doubles import FakeClock, FakeJobQueue
from vidgen.ports.batches import StuckRow
from vidgen.services.requeue import requeue_stuck_rows

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
QUEUES = {"modal-demo": "vidgen.modal-demo", "local-mac": "vidgen.local-mac"}


class Store:
    def __init__(self, rows: list[StuckRow]) -> None:
        self.rows = sorted(rows, key=lambda r: r.row_id)

    def stuck_candidates(self, cutoff: datetime, after: UUID | None, limit: int) -> list[StuckRow]:
        return [r for r in self.rows if after is None or r.row_id > after][:limit]


def run(rows: list[StuckRow], queue: Any, **kwargs: Any) -> Any:
    store = Store(rows)

    class Uow:
        batches = store

        def __enter__(self) -> Uow:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    return requeue_stuck_rows(lambda: Uow(), queue, FakeClock(NOW), **kwargs)  # type: ignore[arg-type]


def test_stuck_rows_of_a_batch_go_to_its_providers_queue_only() -> None:
    """RP-RTE-P5."""
    batch = uuid4()
    rows = [StuckRow(batch, uuid4(), "row", provider_id="modal-demo") for _ in range(3)]
    queue = FakeJobQueue()
    report = run(rows, queue, provider_queues=QUEUES)
    assert report.requeued == 3
    assert queue.queues_used() == {"vidgen.modal-demo"}


def test_two_batches_with_different_providers_are_routed_separately() -> None:
    """RP-RTE-E5."""
    a, b = uuid4(), uuid4()
    rows = [
        StuckRow(a, uuid4(), "row", provider_id="modal-demo"),
        StuckRow(b, uuid4(), "row", provider_id="local-mac"),
    ]
    queue = FakeJobQueue()
    run(rows, queue, provider_queues=QUEUES)
    by_batch = {batch: q for _kind, batch, _row, q in queue.routed}
    assert by_batch == {a: "vidgen.modal-demo", b: "vidgen.local-mac"}


def test_an_old_batch_without_a_provider_uses_the_default_queue() -> None:
    """RP-RTE-E4 (R5): null provider -> no queue name."""
    rows = [StuckRow(uuid4(), uuid4(), "row")]
    queue = FakeJobQueue()
    run(rows, queue, provider_queues=QUEUES)
    assert queue.queues_used() == {None}


def test_a_stuck_preview_is_routed_the_same_way() -> None:
    """RP-RTE-E6."""
    rows = [StuckRow(uuid4(), uuid4(), "preview", provider_id="modal-demo")]
    queue = FakeJobQueue()
    run(rows, queue, provider_queues=QUEUES)
    assert queue.queues_used("preview") == {"vidgen.modal-demo"}


def test_a_provider_missing_from_the_map_falls_back_to_the_default_queue() -> None:
    """RP-RTE-E7: the registry changed after the batch was created; the row is not lost."""
    rows = [StuckRow(uuid4(), uuid4(), "row", provider_id="retired")]
    queue = FakeJobQueue()
    report = run(rows, queue, provider_queues=QUEUES)
    assert report.requeued == 1
    assert queue.queues_used() == {None}
