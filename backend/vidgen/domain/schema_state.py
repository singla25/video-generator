"""Pure comparison of the database's schema revision with the revision the code expects."""

from __future__ import annotations

from enum import StrEnum


class SchemaState(StrEnum):
    """How the database schema relates to the code."""

    OK = "ok"
    BEHIND = "behind"
    AHEAD = "ahead"
    EMPTY = "empty"


def _number(revision: str) -> int | None:
    """The numeric value of a revision id like ``0003``; None when it is not a plain number."""
    text = revision.strip()
    return int(text) if text.isascii() and text.isdigit() else None


def classify(current: str | None, expected: str) -> SchemaState:
    """Compare revisions by number. No revision is empty; an unknown id is behind, never ok."""
    if current is None:
        return SchemaState.EMPTY
    have, want = _number(current), _number(expected)
    if have is None or want is None:
        return SchemaState.BEHIND
    if have == want:
        return SchemaState.OK
    return SchemaState.BEHIND if have < want else SchemaState.AHEAD
