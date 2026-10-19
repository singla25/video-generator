"""Idempotency, redelivery, pause, cancel and concurrency of row jobs (AC12, AC13, A6)."""

from __future__ import annotations

import io
import threading
from datetime import timedelta

import pytest

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.services.render_row import RowOutcomeKind


def render(world: World, number: int = 2):  # type: ignore[no-untyped-def]
    """Render one row of the world."""
    return world.renderer.render(world.batch_id, world.rows[number])


# ---- idempotency ----------------------------------------------------------------------


def test_redelivery_of_a_completed_row_does_nothing(world: World) -> None:
    """TT-AC12-P6: no second render, no duplicate file."""
    render(world)
    files = dict(world.storage.files)
    again = render(world)
    assert again.kind is RowOutcomeKind.NOOP
    assert len(world.encoder.calls) == 1
    assert world.storage.files == files
    assert world.row(2)["attempts"] == 1


def test_output_that_already_exists_means_the_row_is_done(world: World) -> None:
    """TT-AC12-E2: the worker died after storing the file but before saving the status."""
    key = world.expected_key("A1")
    world.storage.write(key, io.BytesIO(b"PRE-EXISTING"))
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.order == []  # nothing re-rendered
    assert world.storage.files[key] == b"PRE-EXISTING"
    assert [
        k for k in world.storage.files if k.startswith("2026-10-18-2/") and k.endswith(".mp4")
    ] == [key]
    assert world.row(2)["status"] == "COMPLETED"
    assert world.row(2)["output_key"] == key


def test_a_row_that_was_processing_when_its_worker_died_is_taken_over(world: World) -> None:
    """TT-AC12-E3: stale PROCESSING (older than the timeout plus margin) is re-claimed."""
    started = world.clock.now() - timedelta(minutes=30)
    world.set_rows([2], status="PROCESSING", started_at=started, attempts=1)
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.row(2)["attempts"] == 2


def test_a_row_processing_right_now_is_left_to_its_worker(world: World) -> None:
    """TT-AC12-E5: not stale -> BUSY, nothing happens."""
    world.set_rows([2], status="PROCESSING", started_at=world.clock.now(), attempts=1)
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.BUSY
    assert world.encoder.calls == []
    assert world.row(2)["status"] == "PROCESSING"


def test_a_crashed_worker_that_used_up_its_attempts_ends_as_failed(world: World) -> None:
    """TT-AC12-N1: attempts counted at claim time survive a hard kill."""
    started = world.clock.now() - timedelta(minutes=30)
    world.set_rows([2], status="PROCESSING", started_at=started, attempts=2)
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert world.encoder.calls == []


@pytest.mark.parametrize("status", ["SKIPPED", "CANCELLED", "FAILED"])
def test_finished_or_cancelled_rows_are_never_rendered(world: World, status: str) -> None:
    """TT-AC12-E10, AC13-P3: stale queue messages are harmless."""
    world.set_rows([2], status=status)
    assert render(world).kind is RowOutcomeKind.NOOP
    assert world.encoder.calls == []
    assert world.row(2)["status"] == status


def test_job_for_a_deleted_batch_is_dropped_quietly(world: World) -> None:
    """TT-AC12-E8."""
    row_id = world.rows[2]
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from vidgen.infrastructure.db.models import Batch

    with Session(world.engine) as session:
        session.execute(delete(Batch).where(Batch.id == world.batch_id))
        session.commit()
    outcome = world.renderer.render(world.batch_id, row_id)
    assert outcome.kind is RowOutcomeKind.NOOP
    assert world.encoder.calls == []


def test_unknown_row_is_dropped_quietly(world: World) -> None:
    """TT-AC12-E8."""
    from uuid import UUID

    assert world.renderer.render(world.batch_id, UUID(int=1)).kind is RowOutcomeKind.NOOP


# ---- concurrency ----------------------------------------------------------------------


def test_two_workers_delivered_the_same_row_render_it_once(world: World) -> None:
    """TT-AC12-E5: row locking; the second delivery is a no-op."""
    world.encoder.delay_s = 0.3
    outcomes: list[RowOutcomeKind] = []

    def work() -> None:
        outcomes.append(render(world).kind)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(o.value for o in outcomes) in (
        sorted([RowOutcomeKind.COMPLETED.value, RowOutcomeKind.BUSY.value]),
        sorted([RowOutcomeKind.COMPLETED.value, RowOutcomeKind.NOOP.value]),
    )
    assert len(world.encoder.calls) == 1
    assert [
        k for k in world.storage.files if k.startswith("2026-10-18-2/") and k.endswith(".mp4")
    ] == [world.expected_key("A1")]
    assert world.row(2)["attempts"] == 1


def test_four_threads_over_ten_rows_render_every_row_exactly_once(
    make_world: WorldFactory,
) -> None:
    """TT-AC12-E4 (two workers' worth of parallelism)."""
    people = [(f"Person {chr(65 + i)}", f"ID{i}") for i in range(10)]
    world = make_world(people)
    world.encoder.delay_s = 0.02
    numbers = list(world.rows)
    results: list[RowOutcomeKind] = []

    def work(chunk: list[int]) -> None:
        for number in chunk:
            results.append(render(world, number).kind)
            results.append(render(world, number).kind)  # duplicate delivery

    threads = [threading.Thread(target=work, args=(numbers[i::4],)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(world.encoder.calls) == 10
    assert set(world.statuses().values()) == {"COMPLETED"}
    assert results.count(RowOutcomeKind.COMPLETED) == 10


# ---- pause and cancel -----------------------------------------------------------------


def test_a_paused_batch_does_not_start_new_rows(make_world: WorldFactory) -> None:
    """TT-AC13-P1: the row stays QUEUED and the job asks to be tried again later."""
    world = make_world(batch_status="PAUSED")
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.DEFERRED
    assert world.encoder.calls == []
    assert world.row(2)["status"] == "QUEUED"
    assert world.row(2)["attempts"] == 0


def test_resuming_lets_the_same_row_run(make_world: WorldFactory) -> None:
    """TT-AC13-P2."""
    world = make_world(batch_status="PAUSED")
    render(world)
    world.set_batch(status="RUNNING")
    assert render(world).kind is RowOutcomeKind.COMPLETED


def test_a_draft_batch_does_not_render_rows(make_world: WorldFactory) -> None:
    """TT-AC7-N1: nothing runs before the batch is started."""
    world = make_world(batch_status="DRAFT")
    assert render(world).kind is RowOutcomeKind.DEFERRED
    assert world.encoder.calls == []


def test_cancelled_batch_does_not_start_queued_rows(make_world: WorldFactory) -> None:
    """TT-AC13-P3 (A6): a stale message for a QUEUED row of a cancelled batch is dropped."""
    world = make_world(batch_status="CANCELLED")
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.NOOP
    assert world.encoder.calls == []
    assert world.row(2)["status"] == "CANCELLED"


def test_a_row_already_processing_when_the_batch_is_cancelled_finishes(world: World) -> None:
    """TT-AC13-P6, E1 (A6)."""
    world.encoder.on_render = lambda: world.set_batch(status="CANCELLED")
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.row(2)["status"] == "COMPLETED"
    assert world.storage.exists(world.expected_key("A1"))
    assert world.batch()["status"] == "CANCELLED"


def test_pausing_during_a_render_lets_that_row_finish(world: World) -> None:
    """TT-AC13-P1: pause only stops rows that have not started."""
    world.encoder.on_render = lambda: world.set_batch(status="PAUSED")
    assert render(world).kind is RowOutcomeKind.COMPLETED
    assert world.batch()["status"] == "PAUSED"
