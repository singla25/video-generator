"""RP-E2E (AC6, AC9): two workers on two queues; a batch routed to provider B is rendered by B only.

Two providers come from a registry file in tmp_path. One in-memory broker stands in for Redis; each
Dramatiq ``Worker`` listens on one provider queue only (like two processes with their own
VIDGEN_QUEUE_NAME). No network, no Modal.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import dramatiq
import pytest
from dramatiq import Worker
from dramatiq.brokers.stub import StubBroker

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.infrastructure.provider_registry import load_registry
from vidgen.infrastructure.queue.dramatiq_queue import DramatiqJobQueue
from vidgen.worker.actors import WorkerConfig, register_actors

TOML = """
[[provider]]
id = "a"
name = "Machine A"
kind = "local"
ai_mode = "fake"

[[provider]]
id = "b"
name = "Machine B"
kind = "local"
ai_mode = "fake"
"""
PEOPLE = [("Asha Verma", "A1"), ("Bina Rao", "B2"), ("Chitra Nair", "C3")]


@pytest.fixture
def broker() -> Iterator[StubBroker]:
    previous = dramatiq.get_broker()
    stub = StubBroker()
    stub.emit_after("process_boot")
    dramatiq.set_broker(stub)
    yield stub
    stub.flush_all()
    stub.close()
    dramatiq.set_broker(previous)


def queues_of(tmp_path: Path) -> dict[str, str]:
    path = tmp_path / "providers.toml"
    path.write_text(TOML, encoding="utf-8")
    registry = load_registry(path, ai_mode="fake", queue_name="vidgen")
    return {p.id: p.queue for p in registry.providers}


def statuses(world: World) -> list[str]:
    return [world.statuses()[n] for n in sorted(world.rows)]


def test_a_batch_routed_to_provider_b_is_rendered_only_by_the_worker_on_b_queue(
    make_world: WorldFactory, broker: StubBroker, tmp_path: Path
) -> None:
    """RP-E2E-P1: worker A is running too, yet never touches B's jobs."""
    world: World = make_world(PEOPLE)
    queues = queues_of(tmp_path)
    assert queues == {"a": "vidgen.a", "b": "vidgen.b"}
    register_actors(broker, world.renderer, WorkerConfig(queue_name=queues["a"]))
    queue = DramatiqJobQueue(broker, queue_name="vidgen")
    queue.enqueue_rows(world.batch_id, list(world.rows.values()), queue_name=queues["b"])
    worker_a = Worker(broker, worker_timeout=50, queues={queues["a"]})
    worker_b = Worker(broker, worker_timeout=50, queues={queues["b"]})
    worker_a.start()
    try:
        broker.join(queues["a"], timeout=5000)
        assert statuses(world) == ["QUEUED"] * 3  # A alone renders nothing of B's batch
        assert queue.depth(queue_name=queues["b"]) == 3
        worker_b.start()
        broker.join(queues["b"], timeout=20_000)
    finally:
        worker_a.stop()
        worker_b.stop()
    assert statuses(world) == ["COMPLETED"] * 3
    assert queue.depth(queue_name=queues["a"]) == 0


def test_a_job_on_queue_a_waits_when_only_worker_b_runs(
    make_world: WorldFactory, broker: StubBroker, tmp_path: Path
) -> None:
    """RP-E2E-N1: a worker on another queue never takes the job (a provider with no worker)."""
    world: World = make_world(PEOPLE)
    queues = queues_of(tmp_path)
    register_actors(broker, world.renderer, WorkerConfig(queue_name=queues["b"]))
    queue = DramatiqJobQueue(broker, queue_name="vidgen")
    queue.enqueue_rows(world.batch_id, [world.rows[2]], queue_name=queues["a"])
    worker_b = Worker(broker, worker_timeout=50, queues={queues["b"]})
    worker_b.start()
    try:
        broker.join(queues["b"], timeout=2000)
        assert world.statuses()[2] == "QUEUED"
        assert queue.depth(queue_name=queues["a"]) == 1
    finally:
        worker_b.stop()
