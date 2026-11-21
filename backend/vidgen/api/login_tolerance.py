"""Let the Admin log in on a completely empty database (BL-8).

Only for the state ``empty`` (no alembic revision, so no tables): the login throttle and audit
tables cannot exist there, and without this the Admin could never reach the status screen.
When the state is ``behind`` the tables exist, so the normal guard and audit writes run
unchanged and brute-force protection is never weakened.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import SQLAlchemyError

from vidgen.api.container import Container
from vidgen.domain.schema_state import SchemaState

logger = logging.getLogger(__name__)
T = TypeVar("T")


def schema_is_empty(app: Container) -> bool:
    """True when the schema check says the database has no migration at all."""
    if app.schema is None:
        return False
    try:
        return app.schema.status().state is SchemaState.EMPTY
    except SQLAlchemyError:
        return False


def tolerant(app: Container, action: Callable[[], T], fallback: T) -> T:
    """Run a login bookkeeping step; skip it only when it fails on an empty database."""
    try:
        return action()
    except SQLAlchemyError as exc:
        if not schema_is_empty(app):
            raise
        logger.warning("login bookkeeping skipped", extra={"error_type": type(exc).__name__})
        return fallback
