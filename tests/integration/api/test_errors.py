"""Error responses: JSON {code, message}, plain language, no traces, no personal data."""

from __future__ import annotations

import logging

import pytest

from tests.fixtures.doubles import CANARY_NAME
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.helpers import analyse, new_template, upload_template
from vidgen.domain.codes import FailureCode, plain_message


def assert_error_shape(response: object, status: int, code: str) -> dict[str, str]:
    """Every error body is exactly {code, message} with a non-empty plain message."""
    assert response.status_code == status  # type: ignore[attr-defined]
    body: dict[str, str] = response.json()  # type: ignore[attr-defined]
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert body["message"].strip()
    for marker in ("Traceback", 'File "', "sqlalchemy", "psycopg", "Exception"):
        assert marker not in body["message"]
    return body


def test_unknown_route_is_a_json_404(env: Env) -> None:
    """Error shape."""
    assert_error_shape(env.client.get("/no/such/route"), 404, "NOT_FOUND")


def test_unauthenticated_request_is_a_json_401(anon: Env) -> None:
    """Error shape, TT-AC16-P6."""
    assert_error_shape(anon.client.get("/templates"), 401, "UNAUTHENTICATED")


def test_failure_code_errors_use_the_plain_language_message(env: Env) -> None:
    """R8: the message is exactly the fixed plain-language text for the code."""
    body = assert_error_shape(
        upload_template(env, content=b"WEBM" + bytes(100)), 422, "UNSUPPORTED_VIDEO"
    )
    assert body["message"] == plain_message(FailureCode.UNSUPPORTED_VIDEO)


def test_validation_errors_do_not_echo_the_submitted_values(env: Env) -> None:
    """C5: a rejected request containing a name must not send that name back."""
    response = env.client.put(
        "/templates/00000000-0000-4000-8000-000000000000/slot",
        json={"start_s": CANARY_NAME, "end_s": CANARY_NAME},
        headers=env.csrf,
    )
    assert response.status_code in (404, 422)
    assert set(response.json()) == {"code", "message"}
    assert CANARY_NAME not in response.text


def test_unexpected_error_is_a_generic_json_500_without_trace_or_pii(
    make_env: EnvFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected exception becomes INTERNAL_ERROR; its text stays out of body and logs."""
    env = make_env(raise_server_exceptions=False)
    env.probe.explode_with = RuntimeError(f"disk exploded for {CANARY_NAME}")
    with caplog.at_level(logging.DEBUG):
        response = upload_template(env)
    body = assert_error_shape(response, 500, "INTERNAL_ERROR")
    assert body["message"] == plain_message(FailureCode.INTERNAL_ERROR)
    assert CANARY_NAME not in response.text
    assert CANARY_NAME not in caplog.text


def test_server_error_does_not_leave_a_half_created_template(make_env: EnvFactory) -> None:
    """Atomicity: a crash after the probe leaves neither a template nor a stored file."""
    env = make_env(raise_server_exceptions=False)
    env.probe.explode_with = RuntimeError("boom")
    upload_template(env)
    assert env.storage.files == {}
    assert env.client.get("/templates").json()["templates"] == []


def test_stt_error_shape(env: Env) -> None:
    """STT_FAILED is a 502 with the standard shape."""
    env.stt.error = RuntimeError("x")
    template_id = new_template(env)
    body = assert_error_shape(analyse(env, template_id), 502, "STT_FAILED")
    assert body["message"] == plain_message(FailureCode.STT_FAILED)


def test_rate_limit_error_shape(anon: Env) -> None:
    """429 has the standard shape and a Retry-After header."""
    for _ in range(5):
        anon.login("bad")
    response = anon.login("bad")
    assert_error_shape(response, 429, "RATE_LIMITED")
    assert "retry-after" in response.headers
