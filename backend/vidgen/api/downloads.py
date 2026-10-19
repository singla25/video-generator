"""Helpers for streaming file responses."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import BinaryIO
from urllib.parse import quote

CHUNK_BYTES = 1024 * 1024
_UNSAFE_ASCII = re.compile(r"[^A-Za-z0-9._-]")


def stream_file(stream: BinaryIO) -> Iterator[bytes]:
    """Yield a stored file in chunks and close it afterwards."""
    with stream:
        while chunk := stream.read(CHUNK_BYTES):
            yield chunk


def attachment_header(filename: str) -> str:
    """``Content-Disposition`` that is pure ASCII yet carries the real name (RFC 5987)."""
    fallback = _UNSAFE_ASCII.sub("_", filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
