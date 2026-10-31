"""Best-effort removal of stored files, run only after the database change is committed."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from vidgen.domain.codes import DomainError
from vidgen.ports import Storage

logger = logging.getLogger(__name__)


def delete_stored(storage: Storage, keys: Iterable[str]) -> None:
    """Delete each key; one stuck file must not stop the rest from being removed.

    Only the number of failures is logged: the keys can reveal batch or template ids.
    """
    failed = 0
    for key in keys:
        try:
            storage.delete(key)
        except (OSError, DomainError):
            failed += 1
    if failed:
        logger.error("some stored files could not be deleted", extra={"failed_files": failed})
