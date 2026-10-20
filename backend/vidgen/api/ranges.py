"""HTTP Range parsing (RFC 9110, single byte ranges only). Pure: no I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeNotSatisfiableError(Exception):
    """The Range header is malformed or lies outside the file (answer 416)."""


@dataclass(frozen=True)
class ByteRange:
    """An inclusive byte range inside a file."""

    start: int
    end: int

    @property
    def length(self) -> int:
        """Number of bytes in the range."""
        return self.end - self.start + 1


def parse_range(header: str | None, size: int) -> ByteRange | None:
    """The requested range, or None when no Range header was sent.

    Handles ``bytes=a-b``, ``bytes=a-`` and ``bytes=-n``. An end beyond the file is cut to the
    last byte. Anything else (several ranges, wrong unit, reversed, outside the file) raises.
    """
    if header is None:
        return None
    match = _RANGE.fullmatch(header.strip())
    if match is None or match.group(1) == match.group(2) == "":
        raise RangeNotSatisfiableError
    first, last = match.groups()
    if first == "":  # suffix range: the last n bytes
        count = int(last)
        if count == 0 or size == 0:
            raise RangeNotSatisfiableError
        return ByteRange(max(size - count, 0), size - 1)
    start = int(first)
    end = size - 1 if last == "" else min(int(last), size - 1)
    if start >= size or end < start:
        raise RangeNotSatisfiableError
    return ByteRange(start, end)
