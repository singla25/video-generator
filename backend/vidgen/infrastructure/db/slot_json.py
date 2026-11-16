"""JSON form of extra name slots in the database: a list of [start_s, end_s] pairs (DD-40).

NULL and an empty list both mean "no extra slots"; reading always gives float pairs.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from vidgen.domain.slot_match import Slot


def slots_to_json(slots: Iterable[Slot]) -> list[list[float]]:
    """The JSON value stored for a set of slots."""
    return [[start_s, end_s] for start_s, end_s in slots]


def slots_from_json(data: Any) -> tuple[Slot, ...]:
    """The slots stored as JSON; None or an empty list gives ()."""
    if not data:
        return ()
    return tuple((float(start_s), float(end_s)) for start_s, end_s in data)
