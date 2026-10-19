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


class DramatiqJobQueue:
    """Enqueues row and preview render jobs on a Dramatiq broker."""

    def __init__(self, broker: Broker, *, queue_name: str = DEFAULT_QUEUE) -> None:
        self._broker = broker
        self._queue = queue_name
        broker.declare_queue(queue_name)

    def enqueue_preview(self, batch_id: UUID, row_id: UUID) -> None:
        """Queue the preview render of one row."""
        self._send(PREVIEW_ACTOR_NAME, batch_id, row_id)

    def enqueue_rows(self, batch_id: UUID, row_ids: list[UUID]) -> None:
        """Queue one render job per row."""
        for row_id in row_ids:
            self._send(ROW_ACTOR_NAME, batch_id, row_id)

    def depth(self) -> int:
        """Messages waiting in the queue (the queue-depth metric)."""
        queues: Any = getattr(self._broker, "queues", None)
        if queues is not None:  # the in-memory StubBroker
            return int(queues[self._queue].qsize())
        client: Any = getattr(self._broker, "client")  # noqa: B009 - Redis broker  # pragma: no cover
        return int(client.llen(f"{REDIS_NAMESPACE}:{self._queue}"))  # pragma: no cover

    def _send(self, actor_name: str, batch_id: UUID, row_id: UUID) -> None:
        message: dramatiq.Message[Any] = dramatiq.Message(
            queue_name=self._queue,
            actor_name=actor_name,
            args=(),
            kwargs={"batch_id": str(batch_id), "row_id": str(row_id)},
            options={},
        )
        self._broker.enqueue(message)
