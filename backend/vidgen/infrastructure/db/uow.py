"""Unit of work: one database session shared by the repositories of one request."""

from __future__ import annotations

from types import TracebackType
from uuid import UUID

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vidgen.infrastructure.db.repositories import (
    AuditRepository,
    SqlTemplateRepository,
    ensure_default_campaign,
)

_ENGINES: dict[str, Engine] = {}


def get_engine(database_url: str) -> Engine:
    """One shared engine (connection pool) per database URL in this process."""
    if database_url not in _ENGINES:
        _ENGINES[database_url] = create_engine(database_url, pool_pre_ping=True, future=True)
    return _ENGINES[database_url]


class SqlUnitOfWork:
    """Opens a session on entry and rolls back on exit unless ``commit`` was called."""

    campaign_id: UUID
    templates: SqlTemplateRepository
    audit: AuditRepository

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self._session: Session | None = None

    def __enter__(self) -> SqlUnitOfWork:
        self._session = self._factory()
        self.campaign_id = ensure_default_campaign(self._session)
        self.templates = SqlTemplateRepository(self._session)
        self.audit = AuditRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._session is not None:
            self._session.close()  # close() rolls back anything uncommitted
            self._session = None

    def commit(self) -> None:
        """Commit the transaction."""
        if self._session is not None:
            self._session.commit()


def uow_factory(database_url: str) -> sessionmaker[Session]:
    """Session factory bound to the shared engine."""
    return sessionmaker(get_engine(database_url), expire_on_commit=False)
