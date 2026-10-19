"""Streaming multipart upload reader with a hard size limit (AC1-N6).

The body is parsed chunk by chunk straight into temporary files. A file that grows past the
limit aborts the request with 413 before anything is stored, and every temporary file is
removed afterwards, whatever happens.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING
from urllib.parse import parse_qs

from fastapi import Request
from python_multipart.multipart import MultipartParser, parse_options_header

from vidgen.api.errors import VALIDATION_ERROR, ApiError

if TYPE_CHECKING:
    from python_multipart.multipart import MultipartCallbacks

PAYLOAD_TOO_LARGE = 413
MULTIPART_OVERHEAD_BYTES = 64 * 1024  # boundaries and headers around the file
MAX_FIELD_BYTES = 8 * 1024
_FORM_DATA = b"multipart/form-data"
_URLENCODED = b"application/x-www-form-urlencoded"
_EXTENSION = re.compile(r"\.[a-z0-9]{1,8}")


def _safe_suffix(raw_filename: bytes) -> str:
    """The file extension of an uploaded name (lower case, plain letters and digits only).

    The extension is kept so the sheet reader can tell .csv from .xlsx; the rest of the
    name is never used.
    """
    suffix = PurePosixPath(
        raw_filename.decode("utf-8", "replace").replace("\\", "/")
    ).suffix.lower()
    return suffix if _EXTENSION.fullmatch(suffix) else ""


class UploadTooLargeError(Exception):
    """A file in the request exceeds the allowed size."""


@dataclass
class ParsedUpload:
    """Text fields and temporary files of one multipart request."""

    fields: dict[str, str] = field(default_factory=dict)
    files: dict[str, Path] = field(default_factory=dict)


class _Collector:
    """Parser callbacks that build a ParsedUpload."""

    def __init__(self, max_file_bytes: int, result: ParsedUpload) -> None:
        self._max = max_file_bytes
        self._result = result
        self._header_name = b""
        self._header_value = b""
        self._headers: dict[bytes, bytes] = {}
        self._name = ""
        self._handle: IO[bytes] | None = None
        self._path: Path | None = None
        self._field = bytearray()
        self._size = 0

    def callbacks(self) -> MultipartCallbacks:
        """Mapping accepted by MultipartParser."""
        return {
            "on_part_begin": self._part_begin,
            "on_header_field": self._header_field,
            "on_header_value": self._header_value_chunk,
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._part_data,
            "on_part_end": self._part_end,
        }

    def _part_begin(self) -> None:
        self._headers = {}
        self._field = bytearray()

    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def _header_value_chunk(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def _header_end(self) -> None:
        self._headers[self._header_name.lower()] = self._header_value
        self._header_name = self._header_value = b""

    def _headers_finished(self) -> None:
        _, options = parse_options_header(self._headers.get(b"content-disposition", b""))
        self._name = options.get(b"name", b"").decode("utf-8", "replace")
        if b"filename" in options:
            fd, name = tempfile.mkstemp(
                prefix="vidgen-upload-", suffix=_safe_suffix(options[b"filename"])
            )
            self._path = Path(name)
            self._handle = os.fdopen(fd, "wb")
            self._size = 0

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if self._handle is None:
            self._field += chunk
            if len(self._field) > MAX_FIELD_BYTES:
                raise ApiError(422, VALIDATION_ERROR)
            return
        self._size += len(chunk)
        if self._size > self._max:
            raise UploadTooLargeError
        self._handle.write(chunk)

    def _part_end(self) -> None:
        if self._handle is not None and self._path is not None:
            self._handle.close()
            self._result.files[self._name] = self._path
            self._handle, self._path = None, None
        else:
            self._result.fields[self._name] = self._field.decode("utf-8", "replace")

    def abort(self) -> None:
        """Close a half-written file (the context manager deletes it)."""
        if self._handle is not None:
            self._handle.close()
            if self._path is not None:
                self._result.files[f"__partial_{self._name}"] = self._path


@contextlib.asynccontextmanager
async def read_upload(request: Request, *, max_file_bytes: int) -> AsyncIterator[ParsedUpload]:
    """Parse a multipart request; temporary files are deleted when the block exits."""
    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    if content_type == _URLENCODED:
        yield await _read_urlencoded(request)
        return
    boundary = options.get(b"boundary")
    if content_type != _FORM_DATA or not boundary:
        raise ApiError(422, VALIDATION_ERROR)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_file_bytes + MULTIPART_OVERHEAD_BYTES:
        raise UploadTooLargeError
    result = ParsedUpload()
    collector = _Collector(max_file_bytes, result)
    parser = MultipartParser(boundary, collector.callbacks())
    try:
        async for chunk in request.stream():
            parser.write(chunk)
        parser.finalize()
        yield result
    finally:
        collector.abort()
        for path in result.files.values():
            path.unlink(missing_ok=True)


async def _read_urlencoded(request: Request) -> ParsedUpload:
    """A form without files (small): read it with a size cap."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_FIELD_BYTES:
            raise ApiError(422, VALIDATION_ERROR)
    parsed = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    return ParsedUpload(fields={key: values[-1] for key, values in parsed.items()})
