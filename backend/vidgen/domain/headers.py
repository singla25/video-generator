"""Header normalisation and column mapping (AC2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.domain.codes import DomainError, FailureCode


class ColumnNotFoundError(DomainError):
    """A mapped column is not in the sheet."""

    def __init__(self, header: str) -> None:
        super().__init__(FailureCode.COLUMN_NOT_FOUND)
        self.header = header


class AmbiguousHeaderError(DomainError):
    """Two sheet headers are equal after normalisation, so the mapping is unclear."""

    def __init__(self, header: str) -> None:
        super().__init__(
            FailureCode.UNSUPPORTED_SHEET,
            f"More than one column is called '{header.strip()}'. Rename one of them.",
        )


class DuplicateMappingError(DomainError):
    """The same column was chosen for two different fields."""

    def __init__(self) -> None:
        super().__init__(
            FailureCode.COLUMN_NOT_FOUND, "Each field needs its own column; two share one."
        )


@dataclass(frozen=True)
class ColumnMapping:
    """Zero-based column indexes of the mapped fields."""

    name_index: int
    id_index: int
    spoken_name_index: int | None = None


def normalize_header(raw: str) -> str:
    """Trim and case-fold a header so ``' VID '`` equals ``'vid'``."""
    return raw.strip().casefold()


def _find_column(normalized: Sequence[str], wanted: str) -> int:
    """Return the index of the single header equal to ``wanted`` (after normalising)."""
    key = normalize_header(wanted)
    matches = [i for i, header in enumerate(normalized) if header == key]
    if not matches:
        raise ColumnNotFoundError(wanted)
    if len(matches) > 1:
        raise AmbiguousHeaderError(wanted)
    return matches[0]


def resolve_mapping(
    headers: Sequence[str], *, name: str, id_: str, spoken_name: str | None = None
) -> ColumnMapping:
    """Map the chosen column names to indexes; each must exist, be unique and be distinct."""
    normalized = [normalize_header(h) for h in headers]
    name_index = _find_column(normalized, name)
    id_index = _find_column(normalized, id_)
    spoken_index = None if spoken_name is None else _find_column(normalized, spoken_name)
    chosen = [i for i in (name_index, id_index, spoken_index) if i is not None]
    if len(set(chosen)) != len(chosen):
        raise DuplicateMappingError
    return ColumnMapping(name_index, id_index, spoken_index)
