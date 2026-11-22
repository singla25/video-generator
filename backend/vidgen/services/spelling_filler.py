"""Fills the missing spoken names of a batch with the transliterator's suggestion (BL-11).

Runs in a worker as a background job, never in a web request. Names and spellings are personal
data: only counts and error types are logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from vidgen.ports.interfaces import Transliterator
from vidgen.ports.rows import SpellingStore

logger = logging.getLogger(__name__)
PAGE_SIZE = 50


@dataclass(frozen=True)
class SpellingReport:
    """How many rows were filled, skipped (blank result or lost race) and failed."""

    filled: int
    skipped: int
    failed: int


class SpellingFiller:
    """Suggests and stores a spoken spelling for every QUEUED row that has none."""

    def __init__(
        self,
        store: SpellingStore,
        transliterator: Transliterator,
        spoken_script: str = "devanagari",
        page_size: int = PAGE_SIZE,
    ) -> None:
        self._store = store
        self._translit = transliterator
        self._script = spoken_script
        self._page_size = page_size

    def fill_missing(self, batch_id: UUID) -> SpellingReport:
        """Fill the batch page by page; safe to run twice. The model is always released."""
        filled = skipped = failed = 0
        try:
            after = 0
            while page := self._store.rows_missing_spoken_name(batch_id, after, self._page_size):
                for row in page:
                    outcome = self._fill_row(row.row_id, row.name)
                    filled += outcome == "filled"
                    skipped += outcome == "skipped"
                    failed += outcome == "failed"
                after = page[-1].row_number  # blank results stay missing: move past them
        finally:
            self._release()
        logger.info(
            "spelling job finished",
            extra={
                "batch_id": str(batch_id),
                "filled": filled,
                "skipped": skipped,
                "failed": failed,
            },
        )
        return SpellingReport(filled, skipped, failed)

    def _fill_row(self, row_id: UUID, name: str) -> str:
        """Store one row's spelling; returns "filled", "skipped" or "failed"."""
        try:
            spoken = self._translit.transliterate(name, self._script)
            if not spoken or not spoken.strip():
                return "skipped"
            return "filled" if self._store.set_spoken_name(row_id, spoken) else "skipped"
        except Exception as exc:  # one bad row must not stop the others
            logger.warning(
                "spelling failed for a row",
                extra={"row_id": str(row_id), "error_type": type(exc).__name__},
            )
            return "failed"

    def _release(self) -> None:
        release = getattr(self._translit, "release", None)
        if callable(release):
            release()
