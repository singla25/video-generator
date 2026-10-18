"""Admin login, session cookie, CSRF and lockout (AC16, ADR-006, A9)."""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from pydantic import SecretStr

from tests.integration.api.conftest import PASSWORD, Env, EnvFactory
from vidgen.api.app import create_app
from vidgen.api.deps import AppDeps

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
OPEN_ROUTES = {("GET", "/health"), ("POST", "/auth/login")}


def set_cookie_headers(response: object) -> list[str]:
    """All Set-Cookie header values of a response."""
    return response.headers.get_list("set-cookie")  # type: ignore[attr-defined, no-any-return]


# ---- positive -------------------------------------------------------------------------


def test_correct_password_logs_in_and_sets_a_hardened_session_cookie(anon: Env) -> None:
    """TT-AC16-P1: HttpOnly, SameSite=strict; not Secure when the setting is off."""
    response = anon.login()
    assert response.status_code == 200
    cookies = {c.split("=", 1)[0]: c for c in set_cookie_headers(response)}
    session = cookies["vidgen_session"].lower()
    assert "httponly" in session
    assert "samesite=strict" in session
    assert "secure" not in session.replace("samesite", "")
    csrf = cookies["vidgen_csrf"].lower()
    assert "httponly" not in csrf  # the page must be able to read it
    assert response.json()["csrf_token"] in cookies["vidgen_csrf"]


def test_session_cookie_is_secure_when_configured(make_env: EnvFactory) -> None:
    """TT-AC16-P1."""
    env = make_env(login=False, cookie_secure=True)
    response = env.client.post("/auth/login", json={"password": PASSWORD})
    session = next(c for c in set_cookie_headers(response) if c.startswith("vidgen_session"))
    assert "secure" in session.lower()


def test_health_and_login_are_open(anon: Env) -> None:
    """TT-AC16-P2."""
    assert anon.client.get("/health").status_code == 200
    assert anon.client.post("/auth/login", json={"password": "x"}).status_code == 401


def test_get_with_session_works_without_csrf(env: Env) -> None:
    """TT-AC16-P4."""
    assert env.client.get("/templates").status_code == 200


def test_state_changing_call_with_session_and_csrf_succeeds(env: Env) -> None:
    """TT-AC16-P3."""
    response = env.client.post("/auth/logout", headers=env.csrf)
    assert response.status_code in (200, 204)


def test_logout_clears_the_cookies_and_closes_the_session(env: Env) -> None:
    """TT-AC16-P5."""
    response = env.client.post("/auth/logout", headers=env.csrf)
    cleared = " ".join(set_cookie_headers(response)).lower()
    assert "vidgen_session" in cleared
    assert ("max-age=0" in cleared) or ("expires=" in cleared)
    assert env.client.get("/templates").status_code == 401


def test_every_route_except_health_and_login_requires_a_session(anon: Env) -> None:
    """TT-AC16-P6: walk app.routes so a forgotten dependency cannot slip through."""
    checked = 0
    for route in anon.app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path.replace("{template_id}", UNKNOWN_ID)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            if (method, route.path) in OPEN_ROUTES:
                continue
            response = anon.client.request(method, path)
            assert response.status_code == 401, f"{method} {route.path} -> {response.status_code}"
            assert response.json()["code"] == "UNAUTHENTICATED"
            checked += 1
    assert checked >= 8


# ---- negative -------------------------------------------------------------------------


def test_wrong_password_is_401_with_a_generic_message(anon: Env) -> None:
    """TT-AC16-N1."""
    response = anon.login("attempt-1234")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "INVALID_CREDENTIALS"
    assert body["message"]
    assert "attempt-1234" not in response.text
    assert not any("vidgen_session" in c for c in set_cookie_headers(response))


def test_state_changing_call_without_csrf_header_is_403(env: Env) -> None:
    """TT-AC16-N2: logout and a slot update both need the double-submit token."""
    logout = env.client.post("/auth/logout")
    assert logout.status_code == 403
    assert logout.json()["code"] == "CSRF_FAILED"
    slot = env.client.put(f"/templates/{UNKNOWN_ID}/slot", json={"start_s": 1.0, "end_s": 1.6})
    assert slot.status_code == 403
    assert slot.json()["code"] == "CSRF_FAILED"


def test_wrong_csrf_token_is_403(env: Env) -> None:
    """TT-AC16-N2."""
    response = env.client.post("/auth/logout", headers={"X-CSRF-Token": "not-the-token"})
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"


def test_csrf_token_from_another_session_is_rejected(make_env: EnvFactory) -> None:
    """TT-AC16-E5."""
    first, second = make_env(), make_env()
    response = first.client.post("/auth/logout", headers=second.csrf)
    assert response.status_code == 403


@pytest.mark.parametrize("cookie", ["garbage", "a.b.c", "", "x" * 500])
def test_garbage_session_cookie_is_401(anon: Env, cookie: str) -> None:
    """TT-AC16-N3."""
    anon.client.cookies.set("vidgen_session", cookie)
    assert anon.client.get("/templates").status_code == 401


def test_tampered_session_cookie_is_401(env: Env) -> None:
    """TT-AC16-N3."""
    value = env.client.cookies["vidgen_session"]
    flipped = value[:-2] + ("A" if value[-2] != "A" else "B") + value[-1]
    env.client.cookies.set("vidgen_session", flipped)
    assert env.client.get("/templates").status_code == 401


def test_cookie_signed_with_another_secret_is_401(make_env: EnvFactory) -> None:
    """TT-AC16-N3."""
    first, second = make_env(), make_env()
    second.client.cookies.set("vidgen_session", first.client.cookies["vidgen_session"])
    assert second.client.get("/templates").status_code == 401


def test_expired_session_is_401_but_a_fresh_one_still_works(env: Env) -> None:
    """TT-AC16-N3: 480 minute lifetime on the injected clock."""
    env.clock.advance(minutes=479)
    assert env.client.get("/templates").status_code == 200
    env.clock.advance(minutes=2)
    assert env.client.get("/templates").status_code == 401


def test_bumping_the_session_version_invalidates_existing_sessions(
    make_env: EnvFactory,
) -> None:
    """ADR-006: server-side session version."""
    first = make_env(session_version=1)
    cookie = first.client.cookies["vidgen_session"]
    second = make_env(login=False, session_version=2, session_secret=first.settings.session_secret)
    second.client.cookies.set("vidgen_session", cookie)
    assert second.client.get("/templates").status_code == 401


def test_password_is_not_stored_or_returned_in_plaintext(env: Env) -> None:
    """TT-AC16-N5."""
    assert PASSWORD not in env.settings.admin_password_hash.get_secret_value()
    assert env.settings.admin_password_hash.get_secret_value().startswith("$argon2")
    assert PASSWORD not in repr(env.settings)


# ---- lockout (A9) ---------------------------------------------------------------------


def test_five_failures_lock_the_login_with_429_and_retry_after(anon: Env) -> None:
    """TT-AC16-N4, E1."""
    for _ in range(4):
        assert anon.login("bad").status_code == 401
    assert anon.login("bad").status_code == 401  # the 5th failure is still a 401
    locked = anon.login("bad")
    assert locked.status_code == 429
    assert locked.json()["code"] == "RATE_LIMITED"
    assert 800 <= int(locked.headers["retry-after"]) <= 900


def test_the_correct_password_is_also_refused_during_the_lockout(anon: Env) -> None:
    """TT-AC16-N4."""
    for _ in range(5):
        anon.login("bad")
    assert anon.login(PASSWORD).status_code == 429


def test_lockout_ends_after_fifteen_minutes(anon: Env) -> None:
    """TT-AC16-E1."""
    for _ in range(5):
        anon.login("bad")
    anon.clock.advance(minutes=14)
    assert anon.login(PASSWORD).status_code == 429
    anon.clock.advance(minutes=2)
    assert anon.login(PASSWORD).status_code == 200


def test_four_failures_do_not_lock_and_success_works(anon: Env) -> None:
    """TT-AC16-E1."""
    for _ in range(4):
        anon.login("bad")
    assert anon.login(PASSWORD).status_code == 200


def test_old_failures_age_out_of_the_fifteen_minute_window(anon: Env) -> None:
    """TT-AC16-E1: 3 + 3 failures spread over 16 minutes never lock."""
    for _ in range(3):
        anon.login("bad")
    anon.clock.advance(minutes=16)
    for _ in range(3):
        assert anon.login("bad").status_code == 401
    assert anon.login(PASSWORD).status_code == 200


# ---- edge -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "password", ["", " ", "\u092a\u093e\u0938\u0935\u0930\u094d\u0921", "p" * 1_000_000]
)
def test_unusual_passwords_are_rejected_without_crashing(anon: Env, password: str) -> None:
    """TT-AC16-E2."""
    response = anon.login(password)
    assert response.status_code in (401, 413, 422)


def test_login_without_a_password_field_is_a_validation_error(anon: Env) -> None:
    """TT-AC16-E2."""
    response = anon.client.post("/auth/login", json={})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_app_refuses_to_start_without_an_admin_password_hash(env: Env) -> None:
    """TT-AC16-E6: there is no default password."""
    broken = env.settings.model_copy(update={"admin_password_hash": SecretStr("")})
    with pytest.raises(ValueError, match="admin"):
        create_app(broken, deps=AppDeps())


def test_multipart_uploads_also_require_csrf(env: Env) -> None:
    """TT-AC16-E7."""
    response = env.client.post("/templates", files={"video": ("t.mp4", b"FAKEVIDEO", "video/mp4")})
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"
