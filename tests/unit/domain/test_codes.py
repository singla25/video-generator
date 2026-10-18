"""Failure codes, plain messages and retryability (R8, A3, A4, B2, B8). Cases TT-AC12-P7 etc."""

from __future__ import annotations

import pytest

from vidgen.domain.codes import FailureCode, is_retryable, plain_message

EXPECTED_CODES = {
    "INVALID_ROW_EMPTY_NAME",
    "INVALID_ROW_EMPTY_ID",
    "DUPLICATE_ID",
    "INVALID_ROW_NAME_TOO_LONG",
    "INVALID_ROW_BAD_CHARACTERS",
    "NAME_TOO_LONG_TO_SPEAK",
    "TTS_FAILED",
    "LIPSYNC_LOW_QUALITY",
    "RENDER_TIMEOUT",
    "STORAGE_ERROR",
    "CONSENT_MISSING",
    "CONTENT_LOCK_VIOLATION",
    "INTERNAL_ERROR",
    "OUTPUT_CHECK_FAILED",
    "SLOT_NOT_FOUND",
    "STT_FAILED",
    "UNSUPPORTED_VIDEO",
    "CORRUPT_VIDEO",
    "UNSUPPORTED_SHEET",
    "COLUMN_NOT_FOUND",
    "CONSENT_FILE_INVALID",
    "INVALID_FOLDER_NAME",
    "NO_COMPLETED_ROWS",
    "IDEMPOTENCY_KEY_CONFLICT",
}


def test_failure_code_set_matches_requirements_exactly() -> None:
    """R8 + A3 + A4 + B2 + B5 + C2: the code list is fixed."""
    assert {c.value for c in FailureCode} == EXPECTED_CODES


def test_failure_code_values_equal_their_names() -> None:
    """Codes are stable strings used in the API and manifest."""
    assert all(c.value == c.name for c in FailureCode)


@pytest.mark.parametrize("code", list(FailureCode))
def test_every_code_has_a_plain_language_message(code: FailureCode) -> None:
    """R8: each code has a non-empty human message with no leftover placeholders."""
    message = plain_message(code)
    assert message.strip()
    assert "{" not in message
    assert code.value not in message  # plain words, not the raw code


def test_duplicate_id_message_names_the_earlier_row() -> None:
    """TT-AC3-N3: message says which earlier row holds the ID."""
    assert "7" in plain_message(FailureCode.DUPLICATE_ID, row=7)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (FailureCode.RENDER_TIMEOUT, True),
        (FailureCode.STORAGE_ERROR, True),
        (FailureCode.INTERNAL_ERROR, False),
        (FailureCode.NAME_TOO_LONG_TO_SPEAK, False),
        (FailureCode.CONSENT_MISSING, False),
        (FailureCode.CONTENT_LOCK_VIOLATION, False),
        (FailureCode.OUTPUT_CHECK_FAILED, False),
        (FailureCode.TTS_FAILED, False),
        (FailureCode.LIPSYNC_LOW_QUALITY, False),
        (FailureCode.DUPLICATE_ID, False),
    ],
)
def test_is_retryable_only_for_timeout_and_storage_codes(code: FailureCode, expected: bool) -> None:
    """TT-AC12-P7, N2: B8 retryable set is {RENDER_TIMEOUT, STORAGE_ERROR}."""
    assert is_retryable(code) is expected


def test_exactly_two_codes_are_retryable() -> None:
    """TT-AC12-P7."""
    assert {c for c in FailureCode if is_retryable(c)} == {
        FailureCode.RENDER_TIMEOUT,
        FailureCode.STORAGE_ERROR,
    }
