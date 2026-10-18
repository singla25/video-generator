"""Output file and folder names (R6.2-R6.4, AC11)."""

from __future__ import annotations

import unicodedata
from collections.abc import Collection
from datetime import date

from vidgen.domain.codes import DomainError, FailureCode

FILE_EXTENSION = ".mp4"
MAX_NAME_BYTES = 255  # common file-system limit per path component
_UNSAFE_FILE_CHARS = frozenset('<>:"/\\|?*')
_FOLDER_FORBIDDEN_CHARS = _UNSAFE_FILE_CHARS
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_ASCII_CONTROL_LIMIT = 0x20
_DELETE_CHAR = 0x7F
_FIRST_SUFFIX = 2


class InvalidFolderNameError(DomainError):
    """A custom output folder name is unsafe or illegal."""

    def __init__(self) -> None:
        super().__init__(FailureCode.INVALID_FOLDER_NAME)


def _is_control(char: str) -> bool:
    """Return True for ASCII control characters, including NUL."""
    return ord(char) < _ASCII_CONTROL_LIMIT or ord(char) == _DELETE_CHAR


def _sanitise(text: str) -> str:
    """Replace unsafe characters and whitespace with ``_``; never start with a dot."""
    cleaned = "".join(
        "_" if c in _UNSAFE_FILE_CHARS or c.isspace() or _is_control(c) else c for c in text
    )
    return "_" + cleaned[1:] if cleaned.startswith(".") else cleaned


def id_key(raw_id: str) -> str:
    """Comparison key for duplicate IDs: trim, sanitise, then case-fold (A2)."""
    return _sanitise(unicodedata.normalize("NFC", raw_id.strip())).casefold()


def output_file_name(raw_id: str) -> str:
    """Return ``<ID>.mp4`` with unsafe characters replaced; capped at 255 bytes."""
    stem = _sanitise(unicodedata.normalize("NFC", raw_id.strip()))
    budget = MAX_NAME_BYTES - len(FILE_EXTENSION.encode())
    while len(stem.encode()) > budget:
        stem = stem[:-1]  # drop whole characters so UTF-8 is never split
    return stem + FILE_EXTENSION


def default_folder_name(day: date, valid_rows: int) -> str:
    """Return ``YYYY-MM-DD-<valid rows>``; a batch needs at least one valid row."""
    if valid_rows < 1:
        raise ValueError("a folder name needs at least one valid row")
    return f"{day.isoformat()}-{valid_rows}"


def _check_folder_name(name: str) -> None:
    """Raise InvalidFolderNameError if ``name`` could escape or break the output area."""
    base = name.split(".", 1)[0].casefold()
    illegal = (
        name in {".", ".."}
        or name.endswith(".")
        or len(name.encode()) > MAX_NAME_BYTES
        or base in _WINDOWS_RESERVED
        or any(c in _FOLDER_FORBIDDEN_CHARS or _is_control(c) for c in name)
    )
    if illegal:
        raise InvalidFolderNameError


def resolve_folder_name(custom: str | None, day: date, valid_rows: int) -> str:
    """Return the validated custom folder name, or the default if it is blank (B4)."""
    name = unicodedata.normalize("NFC", custom or "").strip()
    if not name:
        return default_folder_name(day, valid_rows)
    _check_folder_name(name)
    return name


def unique_folder_name(base: str, existing: Collection[str]) -> str:
    """Return ``base`` or the first free ``base-2``, ``base-3``... (case-insensitive)."""
    taken = {e.casefold() for e in existing}
    candidate, suffix = base, _FIRST_SUFFIX
    while candidate.casefold() in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate
