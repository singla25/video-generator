"""Opt-in warm-up of the local models when the worker starts (T-PROG-BE, item 6).

Each model is loaded once, so broken or missing weights fail at start-up instead of on the first
job, and then released again. Models are never kept in memory by this step.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from vidgen.ports.warmup import Warmable
from vidgen.settings import Settings

logger = logging.getLogger(__name__)


def warm_up_if_enabled(settings: Settings, warmables: Iterable[Warmable]) -> bool:
    """Warm up then release every model when enabled in local mode; returns whether it ran.

    One model at a time: each is released before the next is loaded, so the peak memory stays at
    one model (24 GB Macs). A model that fails to load is still released best-effort; a failure
    is logged and skipped, and start-up goes on.
    """
    if not settings.warm_up_on_start or settings.ai_mode != "local":
        return False
    for model in warmables:
        _attempt(model, "warm_up", model.warm_up)
        _attempt(model, "release", model.release)
    return True


def _attempt(model: Warmable, step: str, action: Callable[[], None]) -> None:
    """Run one step for one model; a failure is logged with its type only, never raised."""
    try:
        action()
    except Exception as exc:
        logger.warning(
            "model warm-up step failed",
            extra={
                "model": type(model).__name__,
                "step": step,
                "error_type": type(exc).__name__,
            },
        )
