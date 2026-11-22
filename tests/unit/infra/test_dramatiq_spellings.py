"""BL-11: the Dramatiq adapter sends the spelling job and the worker actor runs the filler.

Contract names: JobQueue.enqueue_spellings(batch_id), actor SPELLING_ACTOR_NAME == "spell_rows",
register_actors(broker, renderer, config, spelling_filler=None) -> WorkerActors.spell_rows.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import dramatiq
from dramatiq.brokers.stub import StubBroker

from vidgen.infrastructure.queue.dramatiq_queue import (
    DEFAULT_QUEUE,
    SPELLING_ACTOR_NAME,
    DramatiqJobQueue,
)
from vidgen.services.spelling_filler import SpellingReport
from vidgen.worker.actors import WorkerConfig, register_actors


def sent(broker: StubBroker) -> list[dramatiq.Message[Any]]:
    """Messages waiting on the default queue, decoded, without consuming them."""
    queue = broker.queues[DEFAULT_QUEUE]
    return [dramatiq.Message.decode(item) for item in list(queue.queue)]  # type: ignore[arg-type]


class RecordingFiller:
    def __init__(self) -> None:
        self.batches: list[UUID] = []

    def fill_missing(self, batch_id: UUID) -> SpellingReport:
        self.batches.append(batch_id)
        return SpellingReport(0, 0, 0)


def test_the_adapter_sends_one_spelling_message_with_the_batch_id_only() -> None:
    """SP-Q1."""
    broker = StubBroker()
    queue = DramatiqJobQueue(broker)
    batch = uuid4()
    queue.enqueue_spellings(batch)
    messages = sent(broker)
    assert len(messages) == 1
    assert messages[0].actor_name == SPELLING_ACTOR_NAME == "spell_rows"
    assert messages[0].kwargs == {"batch_id": str(batch)}
    assert queue.depth() == 1


def test_spelling_messages_do_not_disturb_row_and_preview_messages() -> None:
    """SP-Q2."""
    broker = StubBroker()
    queue = DramatiqJobQueue(broker)
    queue.enqueue_preview(uuid4(), uuid4())
    queue.enqueue_spellings(uuid4())
    names = sorted(m.actor_name for m in sent(broker))
    assert names == ["render_preview", "spell_rows"]


def test_the_spell_actor_runs_the_filler_for_the_batch() -> None:
    """SP-Q3."""
    broker = StubBroker()
    filler = RecordingFiller()
    actors = register_actors(broker, object(), WorkerConfig(), spelling_filler=filler)  # type: ignore[arg-type]
    batch = uuid4()
    assert actors.spell_rows is not None
    actors.spell_rows.fn(batch_id=str(batch))
    assert filler.batches == [batch]


def test_without_a_filler_there_is_no_spell_actor() -> None:
    """SP-Q4: fake mode workers do not register it."""
    actors = register_actors(StubBroker(), object(), WorkerConfig())  # type: ignore[arg-type]
    assert actors.spell_rows is None


def test_the_spell_actor_is_registered_under_the_queue_actor_name() -> None:
    """SP-Q5: the API sends by name, so the names must match."""
    broker = StubBroker()
    register_actors(broker, object(), WorkerConfig(), spelling_filler=RecordingFiller())  # type: ignore[arg-type]
    assert SPELLING_ACTOR_NAME in broker.actors
