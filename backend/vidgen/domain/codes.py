"""Failure codes, their plain-language messages and retryability (R8, A3, A4, B2, B8)."""

from __future__ import annotations

from enum import StrEnum


class FailureCode(StrEnum):
    """Stable machine codes used in the API, the manifest and the audit log."""

    INVALID_ROW_EMPTY_NAME = "INVALID_ROW_EMPTY_NAME"
    INVALID_ROW_EMPTY_ID = "INVALID_ROW_EMPTY_ID"
    DUPLICATE_ID = "DUPLICATE_ID"
    INVALID_ROW_NAME_TOO_LONG = "INVALID_ROW_NAME_TOO_LONG"
    INVALID_ROW_BAD_CHARACTERS = "INVALID_ROW_BAD_CHARACTERS"
    NAME_TOO_LONG_TO_SPEAK = "NAME_TOO_LONG_TO_SPEAK"
    TTS_FAILED = "TTS_FAILED"
    LIPSYNC_LOW_QUALITY = "LIPSYNC_LOW_QUALITY"
    RENDER_TIMEOUT = "RENDER_TIMEOUT"
    STORAGE_ERROR = "STORAGE_ERROR"
    CONSENT_MISSING = "CONSENT_MISSING"
    CONTENT_LOCK_VIOLATION = "CONTENT_LOCK_VIOLATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    OUTPUT_CHECK_FAILED = "OUTPUT_CHECK_FAILED"
    SLOT_NOT_FOUND = "SLOT_NOT_FOUND"
    SLOTS_INVALID = "SLOTS_INVALID"
    STT_FAILED = "STT_FAILED"
    UNSUPPORTED_VIDEO = "UNSUPPORTED_VIDEO"
    CORRUPT_VIDEO = "CORRUPT_VIDEO"
    UNSUPPORTED_SHEET = "UNSUPPORTED_SHEET"
    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"
    CONSENT_FILE_INVALID = "CONSENT_FILE_INVALID"
    INVALID_FOLDER_NAME = "INVALID_FOLDER_NAME"
    NO_COMPLETED_ROWS = "NO_COMPLETED_ROWS"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    NOT_SELECTED = "NOT_SELECTED"


# The single place for user-facing wording. ``{earlier_row}`` is filled by plain_message.
_MESSAGES: dict[FailureCode, str] = {
    FailureCode.INVALID_ROW_EMPTY_NAME: "The name is empty.",
    FailureCode.INVALID_ROW_EMPTY_ID: "The ID is empty.",
    FailureCode.DUPLICATE_ID: "This ID was already used in {earlier_row}.",
    FailureCode.INVALID_ROW_NAME_TOO_LONG: "The name is longer than the allowed length.",
    FailureCode.INVALID_ROW_BAD_CHARACTERS: (
        "The name contains characters that are not allowed. Use English or Hindi letters, "
        "spaces, dots, hyphens and apostrophes only."
    ),
    FailureCode.NAME_TOO_LONG_TO_SPEAK: "The name takes too long to say within the video.",
    FailureCode.TTS_FAILED: "The voice for this name could not be created.",
    FailureCode.LIPSYNC_LOW_QUALITY: "The lip movement for this name did not look good enough.",
    FailureCode.RENDER_TIMEOUT: "Making this video took too long.",
    FailureCode.STORAGE_ERROR: "The video could not be saved. Please check the free disk space.",
    FailureCode.CONSENT_MISSING: "Consent for this video has not been confirmed.",
    FailureCode.CONTENT_LOCK_VIOLATION: (
        "A change outside the confirmed part of the video was blocked."
    ),
    FailureCode.INTERNAL_ERROR: "Something went wrong while making this video.",
    FailureCode.OUTPUT_CHECK_FAILED: "The finished video did not match the template format.",
    FailureCode.SLOT_NOT_FOUND: "The part of the video to replace could not be found.",
    FailureCode.SLOTS_INVALID: "The name slots overlap or are too close.",
    FailureCode.STT_FAILED: "The speech in the video could not be read.",
    FailureCode.UNSUPPORTED_VIDEO: "This video type is not supported. Use MP4 or MOV.",
    FailureCode.CORRUPT_VIDEO: "This video file looks damaged.",
    FailureCode.UNSUPPORTED_SHEET: "This sheet could not be read. Use .xlsx or .csv.",
    FailureCode.COLUMN_NOT_FOUND: "A selected column was not found in the sheet.",
    FailureCode.CONSENT_FILE_INVALID: "The consent file must be a valid PDF, PNG or JPG.",
    FailureCode.INVALID_FOLDER_NAME: "This folder name is not allowed.",
    FailureCode.NO_COMPLETED_ROWS: "There are no finished videos to download yet.",
    FailureCode.IDEMPOTENCY_KEY_CONFLICT: "This request key was already used for another batch.",
    FailureCode.NOT_SELECTED: "Not selected: outside the number of videos requested.",
}

_RETRYABLE = frozenset({FailureCode.RENDER_TIMEOUT, FailureCode.STORAGE_ERROR})


class DomainError(Exception):
    """Base class for rule violations; carries the failure code for the API and manifest."""

    def __init__(self, code: FailureCode, message: str | None = None) -> None:
        self.code = code
        self.message = message if message is not None else plain_message(code)
        super().__init__(self.message)


def plain_message(code: FailureCode, row: int | None = None) -> str:
    """Return the plain-language message for ``code``; ``row`` names an earlier row."""
    earlier = f"row {row}" if row is not None else "an earlier row"
    return _MESSAGES[code].format(earlier_row=earlier)


def is_retryable(code: FailureCode) -> bool:
    """Return True for codes the queue retries automatically (B8)."""
    return code in _RETRYABLE
