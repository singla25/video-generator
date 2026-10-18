"""Structured JSON logging that only accepts non-personal context."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

_CONTEXT_ATTR = "context"
_HANDLER_MARK = "_vidgen_handler"


class JsonFormatter(logging.Formatter):
    """Format records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Render ``record`` as JSON."""
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, _CONTEXT_ATTR, {}))
        if record.exc_info and record.exc_info[0] is not None:
            # Type only: exception messages may contain personal data.
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not getattr(h, _HANDLER_MARK, False)]
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level)


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    row_id: UUID | None = None,
    row_number: int | None = None,
    batch_id: UUID | None = None,
    template_id: UUID | None = None,
    stage: str | None = None,
    duration_ms: float | None = None,
    attempt: int | None = None,
    code: str | None = None,
) -> None:
    """Log ``message`` with non-PII context only.

    The keyword list is closed on purpose: there is no way to pass a name or ID.
    """
    values: dict[str, Any] = {
        "row_id": row_id,
        "row_number": row_number,
        "batch_id": batch_id,
        "template_id": template_id,
        "stage": stage,
        "duration_ms": duration_ms,
        "attempt": attempt,
        "code": code,
    }
    context = {k: str(v) if isinstance(v, UUID) else v for k, v in values.items() if v is not None}
    logger.log(level, message, extra={_CONTEXT_ATTR: context})
