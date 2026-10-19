"""Streaming video responses with HTTP Range support (DD-19), shared by every video endpoint."""

from __future__ import annotations

from collections.abc import Iterator
from typing import BinaryIO

from fastapi.responses import Response, StreamingResponse

from vidgen.api.ranges import ByteRange, RangeNotSatisfiableError, parse_range

CHUNK_BYTES = 1024 * 1024
VIDEO_TYPE = "video/mp4"
RANGE_NOT_SATISFIABLE = 416


def _size_of(stream: BinaryIO) -> int:
    """File size from the stream itself (seek to the end and back)."""
    size = stream.seek(0, 2)
    stream.seek(0)
    return size


def _chunks(stream: BinaryIO, window: ByteRange) -> Iterator[bytes]:
    """Yield exactly the bytes of ``window`` in chunks and close the stream afterwards."""
    with stream:
        stream.seek(window.start)
        remaining = window.length
        while remaining > 0:
            chunk = stream.read(min(CHUNK_BYTES, remaining))
            remaining -= len(chunk)
            yield chunk


def video_response(
    stream: BinaryIO,
    range_header: str | None,
    *,
    media_type: str = VIDEO_TYPE,
    headers: dict[str, str] | None = None,
) -> Response:
    """200 with the whole file, 206 for a valid Range, or 416 with the file size."""
    size = _size_of(stream)
    extra = {"Accept-Ranges": "bytes", **(headers or {})}
    try:
        window = parse_range(range_header, size)
    except RangeNotSatisfiableError:
        stream.close()
        return Response(
            status_code=RANGE_NOT_SATISFIABLE, headers={**extra, "Content-Range": f"bytes */{size}"}
        )
    whole = ByteRange(0, size - 1)
    partial = window is not None
    window = window or whole
    extra["Content-Length"] = str(window.length)
    if partial:
        extra["Content-Range"] = f"bytes {window.start}-{window.end}/{size}"
    return StreamingResponse(
        _chunks(stream, window),
        status_code=206 if partial else 200,
        media_type=media_type,
        headers=extra,
    )
