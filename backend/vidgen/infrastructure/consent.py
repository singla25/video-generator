"""Content-based type check for consent files (C1): PDF, PNG or JPEG, never by extension."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

PDF_MAGIC = b"%PDF-"
PDF_EOF_MARKER = b"%%EOF"
PDF_EOF_WINDOW = 2048  # the end-of-file marker must be near the end, else the file is cut off
IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg"}
PDF_TYPE = "application/pdf"


def detect_consent_type(path: Path) -> str | None:
    """Return the MIME type of a valid PDF/PNG/JPEG file, or None for anything else."""
    try:
        with path.open("rb") as handle:
            head = handle.read(len(PDF_MAGIC))
            if head == PDF_MAGIC:
                return PDF_TYPE if _pdf_is_complete(path) else None
        return _image_type(path)
    except OSError:
        return None


def _pdf_is_complete(path: Path) -> bool:
    """True if the end-of-file marker appears in the last bytes."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - PDF_EOF_WINDOW))
        return PDF_EOF_MARKER in handle.read()


def _image_type(path: Path) -> str | None:
    """MIME type of an image that decodes completely (catches truncated files)."""
    try:
        with Image.open(path) as image:
            mime = IMAGE_TYPES.get(image.format or "")
            if mime is None:
                return None
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return None
    return mime
