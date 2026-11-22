"""Doubles for the BL-11 spelling tests: a transliterator and an in-memory spelling store.

The store follows the contract of the SpellingStore port (see
docs/test-tree/bl11-spellings-for-all-rows.md): ``rows_missing_spoken_name`` returns QUEUED rows
without a spoken name in row-number order after a cursor, ``set_spoken_name`` is compare-and-set.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from vidgen.ports.rows import MissingSpelling


class FakeTransliterator:
    """Transliterator double that records calls and release; answers from a table or a rule."""

    def __init__(self, answers: dict[str, str | None] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, str]] = []
        self.errors: dict[str, Exception] = {}
        self.released = 0
        self.default: Callable[[str], str | None] = lambda name: f"देव-{name}"

    def transliterate(self, text: str, target_script: str) -> str:
        """Return the canned spelling, the default rule, or raise for a configured name."""
        self.calls.append((text, target_script))
        if text in self.errors:
            raise self.errors[text]
        if text in self.answers:
            return self.answers[text]  # type: ignore[return-value]  # None models a bad adapter
        return self.default(text)  # type: ignore[return-value]

    def release(self) -> None:
        """Count the unload of the model."""
        self.released += 1


@dataclass
class MemRow:
    """One stored row of the in-memory store."""

    row_id: UUID
    row_number: int
    name: str
    spoken: str | None = None
    status: str = "QUEUED"


class InMemorySpellingStore:
    """SpellingStore double for one or more batches."""

    def __init__(self) -> None:
        self.rows: dict[UUID, list[MemRow]] = {}
        self.page_limits: list[int] = []
        self.before_set: Callable[[MemRow], None] | None = None  # simulate a concurrent change
        self.set_errors: dict[str, Exception] = {}

    def add_batch(self, names: list[str], **row_kwargs: object) -> UUID:
        """A batch whose rows are numbered 2.. in order; returns the batch id."""
        batch_id = uuid4()
        self.rows[batch_id] = [
            MemRow(uuid4(), number, name, **row_kwargs)  # type: ignore[arg-type]
            for number, name in enumerate(names, start=2)
        ]
        return batch_id

    def delete_batch(self, batch_id: UUID) -> None:
        """The batch disappears together with its rows."""
        self.rows.pop(batch_id, None)

    def rows_missing_spoken_name(
        self, batch_id: UUID, after: int, limit: int
    ) -> list[MissingSpelling]:
        """QUEUED rows without a spoken name, row number above ``after``, at most ``limit``."""
        self.page_limits.append(limit)
        found = [
            MissingSpelling(r.row_id, r.row_number, r.name)
            for r in self.rows.get(batch_id, [])
            if r.status == "QUEUED" and r.spoken is None and r.row_number > after
        ]
        return sorted(found, key=lambda m: m.row_number)[:limit]

    def set_spoken_name(self, row_id: UUID, spoken: str) -> bool:
        """Store the spelling only if the row is still QUEUED and has none; True when stored."""
        for rows in self.rows.values():
            for row in rows:
                if row.row_id != row_id:
                    continue
                if self.before_set is not None:
                    self.before_set(row)
                if row.name in self.set_errors:
                    raise self.set_errors[row.name]
                if row.status != "QUEUED" or row.spoken is not None:
                    return False
                row.spoken = spoken
                return True
        return False

    def spoken(self, batch_id: UUID) -> list[str | None]:
        """The stored spellings in row order."""
        return [r.spoken for r in self.rows[batch_id]]
