"""BL-12: the authenticated system status shows the active spoken suffix (read-only)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError

from tests.unit.api.test_system_status import KEYS, Beat, Build, DepthQueue, build  # noqa: F401

URL = "/system" + "/status"
SECRET_VALUE = "hunter2-very-secret-marker"  # noqa: S105 - must never appear in the body


def _suffix(make: Build, **overrides: object) -> object:
    response = make(Beat(True), **overrides).get(URL)
    assert response.status_code == 200
    return response.json()["spoken_suffix"]


def test_default_suffix_is_ji(build: Build) -> None:  # noqa: F811
    assert _suffix(build) == "जी"


@pytest.mark.parametrize("value", ["sir", "सर", "Ms."])
def test_custom_suffix_is_reported_as_set(build: Build, value: str) -> None:  # noqa: F811
    assert _suffix(build, spoken_suffix=value) == value


@pytest.mark.parametrize("raw, shown", [("  sir  ", "sir"), ("\tजी \n", "जी")])
def test_surrounding_spaces_are_stripped(build: Build, raw: str, shown: str) -> None:  # noqa: F811
    assert _suffix(build, spoken_suffix=raw) == shown


@pytest.mark.parametrize("raw", ["", "   "])
def test_switched_off_suffix_is_an_empty_string_not_null(build: Build, raw: str) -> None:  # noqa: F811
    assert _suffix(build, spoken_suffix=raw) == ""


@pytest.mark.parametrize("mode", ["fake", "local"])
def test_suffix_is_present_in_every_ai_mode(build: Build, mode: str) -> None:  # noqa: F811
    assert _suffix(build, ai_mode=mode) == "जी"


def test_requires_a_session_and_hides_the_suffix(build: Build) -> None:  # noqa: F811
    response = build(Beat(True), login=False).get(URL)
    assert response.status_code == 401
    assert "spoken_suffix" not in response.text


def test_exact_key_set_with_custom_suffix(build: Build) -> None:  # noqa: F811
    body = build(Beat(True), spoken_suffix="sir").get(URL).json()
    assert set(body) == KEYS


def test_value_follows_the_setting_per_app(build: Build) -> None:  # noqa: F811
    first = build(Beat(True), spoken_suffix="sir")
    second = build(Beat(True), spoken_suffix="")
    third = build(Beat(True))
    assert first.get(URL).json()["spoken_suffix"] == "sir"
    assert second.get(URL).json()["spoken_suffix"] == ""
    assert third.get(URL).json()["spoken_suffix"] == "जी"


def test_suffix_is_reported_when_redis_is_down(build: Build) -> None:  # noqa: F811
    down = RedisConnectionError("down")
    response = build(Beat(down), DepthQueue(down), spoken_suffix="sir").get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["redis_ok"] is False
    assert body["spoken_suffix"] == "sir"


def test_no_other_setting_leaks_into_the_body(build: Build) -> None:  # noqa: F811
    api = build(
        Beat(True),
        spoken_suffix="sir",
        session_secret=SecretStr(SECRET_VALUE),
        creator_entity=f"Org {SECRET_VALUE}",
    )
    response = api.get(URL)
    assert response.status_code == 200
    assert SECRET_VALUE not in response.text
    assert set(response.json()) == KEYS
