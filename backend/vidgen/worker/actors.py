"""Dramatiq actors that run row and preview renders (ADR-002, B8).

The actors are thin: they call the ``RowRenderer`` and translate its outcome into queue
behaviour. Retries are sent explicitly with the configured delay, so the attempt counting stays
in the database and a retried message never doubles the backoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from dramatiq import Actor, Broker

from vidgen.domain.outcomes import RowOutcomeKind
from vidgen.infrastructure.queue.dramatiq_queue import (
    DEFAULT_QUEUE,
    PREVIEW_ACTOR_NAME,
    ROW_ACTOR_NAME,
)
from vidgen.services.render_row import RowOutcome, RowRenderer

if TYPE_CHECKING:
    from vidgen.settings import Settings

MS_PER_SECOND = 1000
WAIT_AGAIN = frozenset({RowOutcomeKind.BUSY, RowOutcomeKind.DEFERRED})


@dataclass(frozen=True)
class WorkerConfig:
    """Queue and retry options (B8: 600 s limit, one retry after 10 s)."""

    queue_name: str = DEFAULT_QUEUE
    max_retries: int = 1
    retry_delay_ms: int = 10_000
    time_limit_ms: int = 600_000
    pause_poll_ms: int = 5_000

    @classmethod
    def from_settings(cls, settings: Settings) -> WorkerConfig:
        """Build the options from application settings."""
        return cls(
            queue_name=settings.queue_name,
            max_retries=settings.max_retries,
            retry_delay_ms=settings.retry_delay_seconds * MS_PER_SECOND,
            time_limit_ms=settings.row_timeout_seconds * MS_PER_SECOND,
            pause_poll_ms=settings.pause_poll_seconds * MS_PER_SECOND,
        )


@dataclass(frozen=True)
class WorkerActors:
    """The registered actors."""

    render_row: Actor[..., None]
    render_preview: Actor[..., None]


def register_actors(broker: Broker, renderer: RowRenderer, config: WorkerConfig) -> WorkerActors:
    """Register the row and preview actors on ``broker``."""
    options = {
        "max_retries": config.max_retries,
        "min_backoff": config.retry_delay_ms,
        "time_limit": config.time_limit_ms,
    }

    def row_job(batch_id: str, row_id: str) -> None:
        outcome = renderer.render(UUID(batch_id), UUID(row_id))
        _again(row_actor, outcome, config, {"batch_id": batch_id, "row_id": row_id})

    def preview_job(batch_id: str, row_id: str, attempt: int = 1) -> None:
        outcome = renderer.render_preview(UUID(batch_id), UUID(row_id), attempt)
        kwargs = {"batch_id": batch_id, "row_id": row_id, "attempt": attempt + 1}
        _again(preview_actor, outcome, config, kwargs)

    row_actor = Actor(
        row_job,
        broker=broker,
        actor_name=ROW_ACTOR_NAME,
        queue_name=config.queue_name,
        priority=0,
        options=dict(options),
    )
    preview_actor = Actor(
        preview_job,
        broker=broker,
        actor_name=PREVIEW_ACTOR_NAME,
        queue_name=config.queue_name,
        priority=0,
        options=dict(options),
    )
    return WorkerActors(row_actor, preview_actor)


def _again(
    actor: Actor[..., None], outcome: RowOutcome, config: WorkerConfig, kwargs: dict[str, object]
) -> None:
    """Send the same job again later when the outcome asks for it."""
    if outcome.kind is RowOutcomeKind.RETRY:
        actor.send_with_options(kwargs=kwargs, delay=int(outcome.delay_s * MS_PER_SECOND))
    elif outcome.kind in WAIT_AGAIN:
        # A busy row is re-checked later: if its worker died, the row becomes stale and is
        # taken over. A paused batch holds its jobs the same way.
        actor.send_with_options(kwargs=kwargs, delay=config.pause_poll_ms)
