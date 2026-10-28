"""System status for the dashboard banner: is the worker running, how many jobs wait."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from redis.exceptions import RedisError

from vidgen.api.deps import container, require_session
from vidgen.ports import JobQueue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_session)])


def _queue_depth(queue: JobQueue) -> int | None:
    """Jobs waiting, or None when Redis cannot answer."""
    try:
        return queue.depth()
    except RedisError as exc:
        logger.warning("queue depth unavailable", extra={"error_type": type(exc).__name__})
        return None


@router.get("/status")
def system_status(request: Request) -> dict[str, Any]:
    """Worker liveness, queue depth and Redis reachability. Never touches the database."""
    app = container(request)
    try:
        worker_alive, redis_ok = app.heartbeat.is_alive(), True
    except RedisError as exc:
        logger.warning("redis unreachable", extra={"error_type": type(exc).__name__})
        worker_alive, redis_ok = False, False
    depth = _queue_depth(app.queue)
    return {"worker_alive": worker_alive, "queue_depth": depth, "redis_ok": redis_ok}
