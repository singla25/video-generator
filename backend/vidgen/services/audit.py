"""Audit trail use cases (C4). Details must never contain personal data (C5)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from vidgen.ports import AuditEntry, Clock, UnitOfWork

UowFactory = Callable[[], AbstractContextManager[UnitOfWork]]

ACTOR_ADMIN = "admin"
ACTOR_ANONYMOUS = "anonymous"
ACTOR_SYSTEM = "system"


class AuditTrail:
    """Writes and reads audit entries, each in its own transaction."""

    def __init__(self, uow: UowFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def record(self, actor: str, action: str, details: dict[str, Any] | None = None) -> None:
        """Append one entry and commit."""
        with self._uow() as uow:
            uow.audit.add(
                campaign_id=uow.campaign_id,
                actor=actor,
                action=action,
                at=self._clock.now(),
                details=details or {},
            )
            uow.commit()

    def entries(self, action: str | None = None) -> list[AuditEntry]:
        """Return entries oldest first, optionally filtered by action."""
        with self._uow() as uow:
            return uow.audit.list(campaign_id=uow.campaign_id, action=action)
