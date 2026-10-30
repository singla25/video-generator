"""Dramatiq adapter for the ``JobQueue`` port (ADR-002).

Messages carry ids only (never names or IDs), because queue payloads are visible in Redis (C5).
The API only sends messages by actor name, so it needs no access to the worker code.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import dramatiq
from dramatiq import Broker

ROW_ACTOR_NAME = "render_row"
PREVIEW_ACTOR_NAME = "render_preview"
DEFAULT_QUEUE = "vidgen"
REDIS_NAMESPACE = "dramatiq"
LIVE_KEY_PREFIX = "vidgen:job:"
LIVE_TTL_SECONDS = 6 * 3600  # long enough for a full queue wait plus render; a flush clears it too


class DramatiqJobQueue:
    """Enqueues row and preview render jobs on a Dramatiq broker."""

    def __init__(self, broker: Broker, *, queue_name: str = DEFAULT_QUEUE) -> None:
        self._broker = broker
        self._queue = queue_name
        broker.declare_queue(queue_name)
        self._local_live: set[UUID] = set()  # used only by brokers without Redis (tests)

    def enqueue_preview(self, batch_id: UUID, row_id: UUID) -> None:
        """Queue the preview render of one row."""
        self._send(PREVIEW_ACTOR_NAME, batch_id, row_id)

    def enqueue_rows(self, batch_id: UUID, row_ids: list[UUID]) -> None:
        """Queue one render job per row."""
        for row_id in row_ids:
            self._send(ROW_ACTOR_NAME, batch_id, row_id)

    def depth(self) -> int:
        """Messages waiting in the queue (the queue-depth metric)."""
        client = self._redis()
        if client is not None:  # Redis broker: its ``queues`` is a plain set of names
            return int(client.llen(f"{REDIS_NAMESPACE}:{self._queue}"))
        queues: Any = self._broker.queues  # the in-memory StubBroker maps name -> Queue
        return int(queues[self._queue].qsize())

    def has_live_job(self, row_id: UUID) -> bool:
        """True while a message for the row was sent and Redis still remembers it.

        A marker key per row is written on enqueue. A Redis flush or restart loses messages and
        markers together, which is exactly the case this answers.
        """
        client = self._redis()
        if client is None:
            return row_id in self._local_live
        return bool(client.exists(f"{LIVE_KEY_PREFIX}{row_id}"))  # pragma: no cover

    def _redis(self) -> Any:
        return getattr(self._broker, "client", None)

    def _mark_live(self, row_id: UUID) -> None:
        client = self._redis()
        if client is None:
            self._local_live.add(row_id)
        else:  # pragma: no cover
            client.set(f"{LIVE_KEY_PREFIX}{row_id}", "1", ex=LIVE_TTL_SECONDS)

    def _send(self, actor_name: str, batch_id: UUID, row_id: UUID) -> None:
        message: dramatiq.Message[Any] = dramatiq.Message(
            queue_name=self._queue,
            actor_name=actor_name,
            args=(),
            kwargs={"batch_id": str(batch_id), "row_id": str(row_id)},
            options={},
        )
        self._broker.enqueue(message)
        self._mark_live(row_id)
