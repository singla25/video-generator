"""Postgres store for the shared login-protection state (D-17).

Every transaction first locks the global row (``SELECT ... FOR UPDATE``), so concurrent
attempts on any number of API instances are handled one after another and no update is lost.
Only counters and timestamps are stored: no passwords, no personal data.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from vidgen.infrastructure.db.models import LoginAttempt
from vidgen.infrastructure.db.repositories import ensure_default_campaign
from vidgen.services.login_guard import GLOBAL_KEY, AttemptState, LoginTransaction

_FIELDS = ("window_started_at", "failure_count", "locked_until", "last_allowed_at")


def _state_of(row: LoginAttempt | None) -> AttemptState:
    """Map a row (or no row) to a state value."""
    if row is None:
        return AttemptState()
    return AttemptState(**{name: getattr(row, name) for name in _FIELDS})


class _Transaction:
    """The two loaded states plus the write-back."""

    def __init__(
        self, session: Session, campaign_id: UUID, client_key: str, client: AttemptState,
        total: AttemptState,
    ) -> None:  # fmt: skip
        self._session = session
        self._campaign_id = campaign_id
        self._client_key = client_key
        self.client = client
        self.total = total

    def save(self, client: AttemptState, total: AttemptState, *, prune_before: datetime) -> None:
        """Write both states (an empty client state removes its row) and prune stale rows."""
        self._upsert(GLOBAL_KEY, total)
        if client.is_empty:
            self._session.execute(
                delete(LoginAttempt).where(
                    LoginAttempt.campaign_id == self._campaign_id,
                    LoginAttempt.client_key == self._client_key,
                )
            )
        else:
            self._upsert(self._client_key, client)
        self._session.execute(
            delete(LoginAttempt).where(
                LoginAttempt.campaign_id == self._campaign_id,
                LoginAttempt.client_key != GLOBAL_KEY,
                func.coalesce(LoginAttempt.locked_until, LoginAttempt.window_started_at)
                < prune_before,
            )
        )

    def _upsert(self, key: str, state: AttemptState) -> None:
        values = {name: getattr(state, name) for name in _FIELDS}
        statement = pg_insert(LoginAttempt).values(
            campaign_id=self._campaign_id, client_key=key, **values
        )
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["campaign_id", "client_key"], set_=values
            )
        )


class SqlLoginStateStore:
    """``LoginStateStore`` on Postgres."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    @contextmanager
    def transaction(self, client_key: str) -> Iterator[LoginTransaction]:
        """Lock the global row, load both states, commit on a clean exit."""
        with self._factory() as session:
            campaign_id = ensure_default_campaign(session)
            session.execute(
                pg_insert(LoginAttempt)
                .values(campaign_id=campaign_id, client_key=GLOBAL_KEY)
                .on_conflict_do_nothing(index_elements=["campaign_id", "client_key"])
            )
            total = self._locked(session, campaign_id, GLOBAL_KEY)
            client = self._locked(session, campaign_id, client_key)
            yield _Transaction(
                session, campaign_id, client_key, _state_of(client), _state_of(total)
            )
            session.commit()

    @staticmethod
    def _locked(session: Session, campaign_id: UUID, key: str) -> LoginAttempt | None:
        query = (
            select(LoginAttempt)
            .where(LoginAttempt.campaign_id == campaign_id, LoginAttempt.client_key == key)
            .with_for_update()
        )
        return session.execute(query).scalar_one_or_none()
