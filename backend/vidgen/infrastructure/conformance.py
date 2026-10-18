"""Static checks that each adapter satisfies its port; mypy verifies these, nothing calls them."""

from __future__ import annotations

from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.ffmpeg.probe import FfprobeVideoProbe
from vidgen.infrastructure.sheets.reader import FileSheetReader
from vidgen.infrastructure.storage.local import LocalStorage
from vidgen.ports import Cipher, SheetReader, Storage, VideoProbe


def _cipher(adapter: AesGcmCipher) -> Cipher:  # pragma: no cover
    return adapter


def _probe(adapter: FfprobeVideoProbe) -> VideoProbe:  # pragma: no cover
    return adapter


def _sheets(adapter: FileSheetReader) -> SheetReader:  # pragma: no cover
    return adapter


def _storage(adapter: LocalStorage) -> Storage:  # pragma: no cover
    return adapter
