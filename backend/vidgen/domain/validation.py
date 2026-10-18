"""Row validation (AC3, A1, A2, B1). Pure rules; limits arrive through ``RowRules``."""

from __future__ import annotations

import string
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import regex

from vidgen.domain.codes import FailureCode, plain_message
from vidgen.domain.naming import id_key

ZWNJ = "\u200c"
ZWJ = "\u200d"
_JOINERS = frozenset({ZWJ, ZWNJ})
_ALLOWED_PUNCTUATION = frozenset(" .-'")
_ASCII_LETTERS = frozenset(string.ascii_letters)
_DEVANAGARI_START = 0x0900
_DEVANAGARI_END = 0x097F
# Danda marks and Devanagari digits are not name characters.
_DEVANAGARI_EXCLUDED = range(0x0964, 0x0970)
_GRAPHEME = regex.compile(r"\X")

# Primary code = first present fault in this order (B1).
_PRIORITY = (
    FailureCode.INVALID_ROW_EMPTY_NAME,
    FailureCode.INVALID_ROW_EMPTY_ID,
    FailureCode.INVALID_ROW_BAD_CHARACTERS,
    FailureCode.INVALID_ROW_NAME_TOO_LONG,
    FailureCode.DUPLICATE_ID,
)


@dataclass(frozen=True)
class RowRules:
    """Validation limits (from settings)."""

    max_name_graphemes: int = 40


@dataclass(frozen=True)
class RowInput:
    """One sheet row; ``row_number`` is the sheet row (header = 1)."""

    row_number: int
    name: str
    id_: str
    spoken_name: str | None = None


@dataclass(frozen=True)
class RowVerdict:
    """Validation result: the primary ``code``, every fault, and the earlier duplicate row."""

    row_number: int
    faults: tuple[FailureCode, ...] = ()
    duplicate_of: int | None = None

    @property
    def valid(self) -> bool:
        """True when the row has no faults."""
        return not self.faults

    @property
    def code(self) -> FailureCode | None:
        """The highest-priority fault, or None for a valid row."""
        return self.faults[0] if self.faults else None

    @property
    def message(self) -> str:
        """Plain-language message for the primary fault; empty for a valid row."""
        return plain_message(self.faults[0], row=self.duplicate_of) if self.faults else ""


def count_graphemes(text: str) -> int:
    """Count user-perceived characters (A1)."""
    return sum(1 for _ in _GRAPHEME.finditer(text))


def effective_spoken_name(name: str, spoken_name: str | None) -> str:
    """Return the trimmed spoken name, falling back to the trimmed name."""
    spoken = (spoken_name or "").strip()
    return spoken or name.strip()


def _is_devanagari_letter(char: str) -> bool:
    """True for Devanagari letters and signs, excluding digits and dandas."""
    point = ord(char)
    return _DEVANAGARI_START <= point <= _DEVANAGARI_END and point not in _DEVANAGARI_EXCLUDED


def _has_bad_characters(text: str) -> bool:
    """True if ``text`` has a character outside Latin/Devanagari/space/. - '."""
    for i, char in enumerate(text):
        if char in _ASCII_LETTERS or char in _ALLOWED_PUNCTUATION or _is_devanagari_letter(char):
            continue
        # Joiners are legal only between Devanagari characters (A1).
        inside_devanagari = (
            char in _JOINERS
            and 0 < i < len(text) - 1
            and _is_devanagari_letter(text[i - 1])
            and _is_devanagari_letter(text[i + 1])
        )
        if not inside_devanagari:
            return True
    return False


def _name_faults(text: str, rules: RowRules) -> set[FailureCode]:
    """Character and length faults of one name field."""
    faults: set[FailureCode] = set()
    if _has_bad_characters(text):
        faults.add(FailureCode.INVALID_ROW_BAD_CHARACTERS)
    if count_graphemes(text) > rules.max_name_graphemes:
        faults.add(FailureCode.INVALID_ROW_NAME_TOO_LONG)
    return faults


class RowValidator:
    """Validates rows one by one, remembering IDs of valid rows to find duplicates (A2)."""

    def __init__(self, rules: RowRules) -> None:
        self._rules = rules
        self._first_row_by_key: dict[str, int] = {}

    def validate(self, row: RowInput) -> RowVerdict:
        """Validate ``row`` against the rules and the rows seen so far."""
        name, raw_id = row.name.strip(), row.id_.strip()
        found: set[FailureCode] = set()
        if not name:
            found.add(FailureCode.INVALID_ROW_EMPTY_NAME)
        if not raw_id:
            found.add(FailureCode.INVALID_ROW_EMPTY_ID)
        found |= _name_faults(name, self._rules)
        if row.spoken_name and row.spoken_name.strip():
            found |= _name_faults(row.spoken_name.strip(), self._rules)

        key = id_key(raw_id)
        duplicate_of = self._first_row_by_key.get(key) if raw_id else None
        if duplicate_of is not None:
            found.add(FailureCode.DUPLICATE_ID)
        elif raw_id and not found:
            self._first_row_by_key[key] = row.row_number
        return RowVerdict(row.row_number, tuple(c for c in _PRIORITY if c in found), duplicate_of)


def validate_rows(rows: Iterable[RowInput], rules: RowRules) -> Iterator[RowVerdict]:
    """Lazily validate a stream of rows in order."""
    validator = RowValidator(rules)
    for row in rows:
        yield validator.validate(row)
