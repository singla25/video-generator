"""Helpers for download response headers."""

from __future__ import annotations

import re
from urllib.parse import quote

_UNSAFE_ASCII = re.compile(r"[^A-Za-z0-9._-]")


def attachment_header(filename: str) -> str:
    """``Content-Disposition`` that is pure ASCII yet carries the real name (RFC 5987)."""
    fallback = _UNSAFE_ASCII.sub("_", filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
