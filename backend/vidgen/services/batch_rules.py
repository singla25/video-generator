"""Small pure rules used by the batch services. Stdlib only, no I/O."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, timedelta
from typing import TypeVar

from vidgen.domain.stats import StatusCounts
from vidgen.domain.status import ApprovalFingerprint
from vidgen.ports.batches import DayStat, MappingRecord
from vidgen.ports.models import TemplateRecord

T = TypeVar("T")
PERCENT = 100.0
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralise_cell(text: str) -> str:
    """Prefix a quote to text a spreadsheet could execute as a formula (CSV injection)."""
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def matches_search(query: str, *fields: str | None) -> bool:
    """Case-insensitive substring match against any field (B6)."""
    needle = query.casefold()
    return any(needle in field.casefold() for field in fields if field)


def page_count(total: int, page_size: int) -> int:
    """Number of pages needed for ``total`` items."""
    return math.ceil(total / page_size)


def progress_percent(counts: StatusCounts) -> float:
    """Share of rows that are no longer waiting or running."""
    return PERCENT * (counts.total - counts.remaining) / max(counts.total, 1)


def counts_from(by_status: Mapping[str, int]) -> StatusCounts:
    """Build the seven overview counts from a status-to-count mapping."""
    return StatusCounts(
        total=sum(by_status.values()),
        completed=by_status.get("COMPLETED", 0),
        processing=by_status.get("PROCESSING", 0),
        queued=by_status.get("QUEUED", 0),
        failed=by_status.get("FAILED", 0),
        skipped=by_status.get("SKIPPED", 0),
        cancelled=by_status.get("CANCELLED", 0),
    )


def fingerprint_for(template: TemplateRecord, mapping: MappingRecord | None) -> ApprovalFingerprint:
    """What a preview approval depends on: slot, template and column mapping (A5)."""
    start, end = template.slot or (0.0, 0.0)
    indexes = mapping.indexes if mapping else ()
    return ApprovalFingerprint(start, end, str(template.id), indexes)


def day_series(
    last_day: date, days: int, stats: Mapping[date, DayStat]
) -> list[tuple[date, DayStat]]:
    """``days`` consecutive days ending at ``last_day``; days without videos count zero."""
    first = last_day - timedelta(days=days - 1)
    series = [first + timedelta(days=offset) for offset in range(days)]
    return [(day, stats.get(day, DayStat(0, None))) for day in series]
