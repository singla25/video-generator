"""System status for the dashboard banner: is the worker running, how many jobs wait."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from vidgen.api.deps import container, require_session
from vidgen.ports import JobQueue
from vidgen.services.schema_check import SchemaCheck

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_session)])


def _queue_depth(queue: JobQueue) -> int | None:
    """Jobs waiting, or None when Redis cannot answer."""
    try:
        return queue.depth()
    except RedisError as exc:
        logger.warning("queue depth unavailable", extra={"error_type": type(exc).__name__})
        return None


def _schema_block(check: SchemaCheck | None) -> dict[str, Any] | None:
    """Schema state for the banner; None when there is no check or the database cannot answer."""
    if check is None:
        return None
    try:
        status = check.status()
    except SQLAlchemyError as exc:
        logger.warning("schema check unavailable", extra={"error_type": type(exc).__name__})
        return None
    return {
        "state": status.state.value,
        "current": status.current,
        "expected": status.expected,
        "message": status.message,
    }


@router.get("/status")
def system_status(request: Request) -> dict[str, Any]:
    """Worker liveness, queue depth, Redis reachability and the schema state."""
    app = container(request)
    try:
        worker_alive, redis_ok = app.heartbeat.is_alive(), True
    except RedisError as exc:
        logger.warning("redis unreachable", extra={"error_type": type(exc).__name__})
        worker_alive, redis_ok = False, False
    depth = _queue_depth(app.queue)
    schema = _schema_block(app.schema)
    body: dict[str, Any] = {
        "worker_alive": worker_alive,
        "queue_depth": depth,
        "redis_ok": redis_ok,
        "ai_mode": app.settings.ai_mode,
    }
    if app.schema is not None:  # no check configured: the key is left out
        body["schema"] = schema
    return body
