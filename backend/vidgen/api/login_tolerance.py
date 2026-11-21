"""Let the Admin log in while the database is behind (login bookkeeping tables may be missing)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import SQLAlchemyError

from vidgen.api.container import Container

logger = logging.getLogger(__name__)
T = TypeVar("T")


def schema_blocks(app: Container) -> bool:
    """True when the schema check says the database needs a migration (False if unreadable)."""
    try:
        return app.schema.status().blocks
    except SQLAlchemyError:
        return False


def tolerant(app: Container, action: Callable[[], T], fallback: T) -> T:
    """Run a login bookkeeping step; when it fails only because the schema is behind, skip it."""
    try:
        return action()
    except SQLAlchemyError as exc:
        if not schema_blocks(app):
            raise
        logger.warning("login bookkeeping skipped", extra={"error_type": type(exc).__name__})
        return fallback
