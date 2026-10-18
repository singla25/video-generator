"""Dramatiq actors and the queue adapter on a StubBroker (ADR-002, AC12, AC13, D-19)."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import dramatiq
import pytest
from dramatiq import Worker
from dramatiq.brokers.stub import StubBroker

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from tests.integration.api.conftest import make_settings
from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.retry import WorkerCrashedError
from vidgen.infrastructure.queue.dramatiq_queue import (
    PREVIEW_ACTOR_NAME,
    ROW_ACTOR_NAME,
    DramatiqJobQueue,
)
from vidgen.worker.actors import WorkerActors, WorkerConfig, register_actors

QUEUE = "vidgen-test"
FAST = WorkerConfig(queue_name=QUEUE, max_retries=1, retry_delay_ms=20, pause_poll_ms=40)


@pytest.fixture
def broker() -> Iterator[StubBroker]:
    """A fresh in-memory broker; the global broker is restored afterwards."""
    previous = dramatiq.get_broker()
    stub = StubBroker()
    stub.emit_after("process_boot")
    dramatiq.set_broker(stub)
    yield stub
    stub.flush_all()
    stub.close()
    dramatiq.set_broker(previous)


@contextlib.contextmanager
def running_workers(broker: StubBroker, threads: int = 1, workers: int = 1) -> Iterator[None]:
    """Start Dramatiq workers on the broker for the duration of the block."""
    started = [Worker(broker, worker_timeout=50, worker_threads=threads) for _ in range(workers)]
    for worker in started:
        worker.start()
    try:
        yield
    finally:
        for worker in started:
            worker.stop()


def drain(broker: StubBroker) -> None:
    """Wait until every message (including retries and delays) has been handled."""
    broker.join(QUEUE, timeout=20_000)


def setup(
    world: World, broker: StubBroker, config: WorkerConfig = FAST
) -> tuple[WorkerActors, DramatiqJobQueue]:
    """Register the actors for ``world`` and create the queue adapter."""
    actors = register_actors(broker, world.renderer, config)
    return actors, DramatiqJobQueue(broker, queue_name=config.queue_name)


# ---- configuration --------------------------------------------------------------------


def test_default_worker_config_follows_b8() -> None:
    """TT-AC12-E6 (B8): 600 s limit, one retry after 10 s."""
    config = WorkerConfig()
    assert config.max_retries == 1
    assert config.retry_delay_ms == 10_000
    assert config.time_limit_ms == 600_000


def test_worker_config_is_built_from_settings(db, test_db_url: str, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """TT-AC12-E6: values come from settings, not constants."""
    settings = make_settings(
        test_db_url, tmp_path, row_timeout_seconds=90, retry_delay_seconds=3, max_retries=2
    )
    config = WorkerConfig.from_settings(settings)
    assert (config.time_limit_ms, config.retry_delay_ms, config.max_retries) == (90_000, 3_000, 2)


def test_actors_carry_the_retry_and_time_limit_options(world: World, broker: StubBroker) -> None:
    """TT-AC12-P2, P3: Dramatiq options match the configuration."""
    actors = register_actors(broker, world.renderer, WorkerConfig(queue_name=QUEUE))
    for actor in (actors.render_row, actors.render_preview):
        assert actor.options["max_retries"] == 1
        assert actor.options["min_backoff"] == 10_000
        assert actor.options["time_limit"] == 600_000
        assert actor.queue_name == QUEUE
    assert actors.render_row.actor_name == ROW_ACTOR_NAME
    assert actors.render_preview.actor_name == PREVIEW_ACTOR_NAME


# ---- queue adapter --------------------------------------------------------------------


def test_enqueue_rows_puts_one_message_per_row_on_the_queue(
    make_world: WorldFactory, broker: StubBroker
) -> None:
    """D-19: the JobQueue adapter."""
    world = make_world([("Asha", "A1"), ("Bina", "B2"), ("Chand", "C3")])
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))
    assert queue.depth() == 3
    messages = list(broker.queues[QUEUE].queue)
    assert {m.actor_name for m in messages} == {ROW_ACTOR_NAME}
    assert {UUID(m.kwargs["row_id"]) for m in messages} == set(world.rows.values())
    assert {UUID(m.kwargs["batch_id"]) for m in messages} == {world.batch_id}


def test_enqueue_preview_sends_a_preview_message(world: World, broker: StubBroker) -> None:
    """D-19."""
    _, queue = setup(world, broker)
    queue.enqueue_preview(world.batch_id, world.rows[2])
    message = broker.queues[QUEUE].queue[0]
    assert message.actor_name == PREVIEW_ACTOR_NAME
    assert UUID(message.kwargs["row_id"]) == world.rows[2]


def test_messages_carry_only_ids_never_personal_data(
    make_world: WorldFactory, broker: StubBroker
) -> None:
    """TT-AC17-P4: queue payloads are visible in Redis."""
    world = make_world([(CANARY_NAME.replace("-", " "), CANARY_ID)])
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))
    queue.enqueue_preview(world.batch_id, world.rows[2])
    text = "".join(repr(m.asdict()) for m in broker.queues[QUEUE].queue)
    assert "Canary" not in text
    assert "CANARY1" not in text


def test_enqueue_of_no_rows_sends_nothing(world: World, broker: StubBroker) -> None:
    """TT-AC13-N3."""
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, [])
    assert queue.depth() == 0


def test_queue_depth_metric_counts_waiting_messages_and_returns_to_zero(
    make_world: WorldFactory, broker: StubBroker
) -> None:
    """TT-AC12-E9: the queue-depth metric."""
    world = make_world([(f"Person {c}", f"ID{c}") for c in "ABCD"])
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))
    assert queue.depth() == 4
    with running_workers(broker):
        drain(broker)
    assert queue.depth() == 0


# ---- processing -----------------------------------------------------------------------


def test_actor_renders_every_enqueued_row(make_world: WorldFactory, broker: StubBroker) -> None:
    """TT-AC12-P1: rows are independent jobs."""
    world = make_world([(f"Person {c}", f"ID{c}") for c in "ABCDE"])
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))
    with running_workers(broker):
        drain(broker)
    assert set(world.statuses().values()) == {"COMPLETED"}
    assert world.batch()["status"] == "COMPLETED"
    assert len(world.encoder.calls) == 5


def test_crash_is_retried_exactly_once_after_the_delay(world: World, broker: StubBroker) -> None:
    """TT-AC12-P2 (B8)."""
    world.encoder.errors = [WorkerCrashedError()]
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, [world.rows[2]])
    with running_workers(broker):
        drain(broker)
    assert world.row(2)["status"] == "COMPLETED"
    assert world.row(2)["attempts"] == 2
    assert len(world.encoder.calls) == 2


def test_a_second_crash_fails_the_row_with_no_third_attempt(
    world: World, broker: StubBroker
) -> None:
    """TT-AC12-N1."""
    world.encoder.errors = [WorkerCrashedError(), WorkerCrashedError(), WorkerCrashedError()]
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, [world.rows[2]])
    with running_workers(broker):
        drain(broker)
    assert world.row(2)["status"] == "FAILED"
    assert world.row(2)["failure_code"] == "INTERNAL_ERROR"
    assert len(world.encoder.calls) == 2


def test_timeout_is_retried_once(world: World, broker: StubBroker) -> None:
    """TT-AC12-P3."""
    world.encoder.errors = [DomainError(FailureCode.RENDER_TIMEOUT)]
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, [world.rows[2]])
    with running_workers(broker):
        drain(broker)
    assert world.row(2)["status"] == "COMPLETED"
    assert len(world.encoder.calls) == 2


def test_storage_error_is_retried_once(world: World, broker: StubBroker) -> None:
    """TT-AC12-P4."""
    world.storage.fail_next = 1
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, [world.rows[2]])
    with running_workers(broker):
        drain(broker)
    assert world.row(2)["status"] == "COMPLETED"
    assert world.row(2)["attempts"] == 2


def test_quality_failure_is_not_retried(world: World, broker: StubBroker) -> None:
    """TT-AC12-N2."""
    world.quality.result = ["X"]
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, [world.rows[2]])
    with running_workers(broker):
        drain(broker)
    assert world.row(2)["status"] == "FAILED"
    assert world.row(2)["failure_code"] == "OUTPUT_CHECK_FAILED"
    assert len(world.encoder.calls) == 1


def test_duplicate_messages_for_one_row_render_it_once(world: World, broker: StubBroker) -> None:
    """TT-AC12-P6: at-least-once delivery."""
    _, queue = setup(world, broker)
    for _ in range(3):
        queue.enqueue_rows(world.batch_id, [world.rows[2]])
    with running_workers(broker):
        drain(broker)
    assert len(world.encoder.calls) == 1
    assert [k for k in world.storage.files if k.startswith("2026-10-18-2/A1")] == [
        world.expected_key("A1")
    ]


def test_messages_of_cancelled_rows_do_nothing(
    make_world: WorldFactory, broker: StubBroker
) -> None:
    """TT-AC13-P3 (A6)."""
    world = make_world([("Asha", "A1"), ("Bina", "B2")], batch_status="CANCELLED")
    world.set_rows([2, 3], status="CANCELLED")
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))
    with running_workers(broker):
        drain(broker)
    assert world.encoder.calls == []
    assert set(world.statuses().values()) == {"CANCELLED"}


def test_paused_batch_holds_its_rows_until_it_is_resumed(
    make_world: WorldFactory, broker: StubBroker
) -> None:
    """TT-AC13-P1, P2: no new row starts while paused; resuming lets the same jobs run."""
    world = make_world([("Asha", "A1"), ("Bina", "B2")], batch_status="PAUSED")
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))
    with running_workers(broker):
        time.sleep(0.5)
        assert world.encoder.calls == []
        assert set(world.statuses().values()) == {"QUEUED"}
        world.set_batch(status="RUNNING")
        drain(broker)
    assert set(world.statuses().values()) == {"COMPLETED"}


def test_two_workers_never_render_a_row_twice(make_world: WorldFactory, broker: StubBroker) -> None:
    """TT-AC12-E4: two worker processes' worth of threads on one queue."""
    world = make_world([(f"Person {chr(65 + i)}", f"ID{i}") for i in range(12)])
    world.encoder.delay_s = 0.02
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))
    queue.enqueue_rows(world.batch_id, list(world.rows.values()))  # duplicates on purpose
    with running_workers(broker, threads=2, workers=2):
        drain(broker)
    assert len(world.encoder.calls) == 12
    assert set(world.statuses().values()) == {"COMPLETED"}


def test_preview_message_renders_and_reports(world: World, broker: StubBroker) -> None:
    """TT-AC7-P1: the preview goes through the queue."""
    _, queue = setup(world, broker)
    queue.enqueue_preview(world.batch_id, world.rows[2])
    with running_workers(broker):
        drain(broker)
    assert world.previews.rendered == [(world.batch_id, f"previews/{world.batch_id}.mp4")]
    assert world.row(2)["status"] == "QUEUED"


def test_failed_preview_after_retry_is_reported_once(world: World, broker: StubBroker) -> None:
    """TT-AC7-E4."""
    world.encoder.errors = [WorkerCrashedError(), WorkerCrashedError()]
    _, queue = setup(world, broker)
    queue.enqueue_preview(world.batch_id, world.rows[2])
    with running_workers(broker):
        drain(broker)
    assert len(world.previews.failed) == 1
    assert world.previews.rendered == []


def test_worker_logs_contain_no_personal_data(
    make_world: WorldFactory, broker: StubBroker, caplog: pytest.LogCaptureFixture
) -> None:
    """TT-AC17-P4: the whole path, including a crash with a name in the exception text."""
    world = make_world([(CANARY_NAME.replace("-", " "), CANARY_ID)])
    world.encoder.errors = [WorkerCrashedError(f"died while rendering {CANARY_NAME}")]
    _, queue = setup(world, broker)
    queue.enqueue_rows(world.batch_id, [world.rows[2]])
    with caplog.at_level(logging.DEBUG), running_workers(broker):
        drain(broker)
    assert "Canary" not in caplog.text
    assert "CANARY1" not in caplog.text
