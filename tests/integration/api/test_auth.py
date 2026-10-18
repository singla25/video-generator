"""Admin login, session cookie, CSRF and lockout (AC16, ADR-006, A9)."""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
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


# ---- lockout (A9, D-15) ---------------------------------------------------------------


def fail_login(client: TestClient, **headers: str) -> int:
    """POST a wrong-password login from ``client`` and return the status code."""
    return client.post("/auth/login", json={"password": "bad"}, headers=headers).status_code


def test_five_failures_from_one_client_lock_it_with_429_and_retry_after(anon: Env) -> None:
    """TT-AC16-N4, E1 (D-15): per-client lockout."""
    for _ in range(5):
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


def test_a_locked_client_does_not_lock_out_other_clients(anon: Env) -> None:
    """D-15: an attacker cannot lock the admin out from another address."""
    for _ in range(6):
        anon.login("bad")
    assert anon.login(PASSWORD).status_code == 429
    admin = anon.client_from("10.0.0.2")
    response = admin.post("/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200


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


def trip_global_cap(env: Env, count: int = 50, prefix: str = "10.1.0") -> None:
    """Fail ``count`` logins, each from a different address."""
    for number in range(count):
        assert fail_login(env.client_from(f"{prefix}.{number + 1}")) == 401


def login_from(env: Env, address: str, password: str = PASSWORD) -> int:
    """Status of a login attempt from ``address``."""
    client = env.client_from(address)
    return client.post("/auth/login", json={"password": password}).status_code


def test_fifty_failures_from_many_clients_throttle_every_login(anon: Env) -> None:
    """D-15 (2): the global cap throttles, it does not lock."""
    trip_global_cap(anon)
    response = anon.client_from("10.9.9.9").post("/auth/login", json={"password": PASSWORD})
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert 1 <= int(response.headers["retry-after"]) <= 5


def test_forty_nine_failures_do_not_throttle(anon: Env) -> None:
    """D-15: boundary."""
    trip_global_cap(anon, 49)
    assert login_from(anon, "10.9.9.9") == 200
    assert login_from(anon, "10.9.9.10") == 200  # no rate limit either


def test_correct_password_succeeds_once_the_gap_has_passed_during_the_throttle(
    anon: Env,
) -> None:
    """D-15 (2): an attacker can slow the admin's login but never block it."""
    trip_global_cap(anon)
    anon.clock.advance(seconds=5)
    assert login_from(anon, "10.9.9.9") == 200


def test_a_second_attempt_within_the_gap_is_refused_even_with_the_right_password(
    anon: Env,
) -> None:
    """D-15 (2): 1 attempt per 5 s globally."""
    trip_global_cap(anon)
    anon.clock.advance(seconds=5)
    assert login_from(anon, "10.9.9.9") == 200
    anon.clock.advance(seconds=4)
    assert login_from(anon, "10.9.9.10") == 429
    anon.clock.advance(seconds=1)
    assert login_from(anon, "10.9.9.10") == 200


def test_throttle_ends_after_fifteen_minutes(anon: Env) -> None:
    """D-15 (2)."""
    trip_global_cap(anon)
    anon.clock.advance(minutes=14)
    assert login_from(anon, "10.9.9.9") == 200  # allowed (gap passed), still inside the window
    assert login_from(anon, "10.9.9.10") == 429
    anon.clock.advance(minutes=2)
    assert login_from(anon, "10.9.9.10") == 200
    assert login_from(anon, "10.9.9.11") == 200  # no throttle any more


def test_existing_sessions_are_not_affected_by_locks_or_throttling(make_env: EnvFactory) -> None:
    """D-15 (3): a client logged in before the attack keeps working."""
    env = make_env()  # logged in as "testclient"
    trip_global_cap(env)
    for _ in range(6):
        fail_login(env.client_from("10.5.5.5"))
    assert env.client.get("/templates").status_code == 200
    assert env.client.get("/audit").status_code == 200
    assert env.client.post("/auth/logout", headers=env.csrf).status_code in (200, 204)


def test_crossing_the_global_cap_writes_exactly_one_alert_per_window(make_env: EnvFactory) -> None:
    """D-15 (4): SECURITY_LOGIN_THROTTLED, once, without passwords or personal data."""
    env = make_env()
    trip_global_cap(env, 49)
    alerts = env.client.get("/audit", params={"action": "SECURITY_LOGIN_THROTTLED"})
    assert alerts.json()["entries"] == []
    trip_global_cap(env, 5, prefix="10.2.0")  # crosses the cap; later failures add nothing
    entries = env.client.get("/audit", params={"action": "SECURITY_LOGIN_THROTTLED"}).json()[
        "entries"
    ]
    assert len(entries) == 1
    assert entries[0]["actor"] == "system"
    assert PASSWORD not in str(entries)


def test_a_new_window_writes_a_new_alert(make_env: EnvFactory) -> None:
    """D-15 (4): one event per window."""
    env = make_env()
    trip_global_cap(env)
    env.clock.advance(minutes=16)
    trip_global_cap(env, prefix="10.3.0")
    entries = env.client.get("/audit", params={"action": "SECURITY_LOGIN_THROTTLED"}).json()[
        "entries"
    ]
    assert len(entries) == 2


def test_x_forwarded_for_cannot_split_the_per_client_count(anon: Env) -> None:
    """D-15: the direct peer is the client; spoofed headers change nothing."""
    for number in range(5):
        assert fail_login(anon.client, **{"X-Forwarded-For": f"203.0.113.{number}"}) == 401
    assert fail_login(anon.client, **{"X-Forwarded-For": "198.51.100.7"}) == 429


def test_x_forwarded_for_cannot_be_used_to_escape_a_lockout(anon: Env) -> None:
    """D-15."""
    for _ in range(5):
        anon.login("bad")
    response = anon.client.post(
        "/auth/login",
        json={"password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.99", "X-Real-IP": "198.51.100.99"},
    )
    assert response.status_code == 429


def test_x_forwarded_for_does_not_lock_an_innocent_peer(anon: Env) -> None:
    """D-15: pretending to be the admin's address from elsewhere does not lock the admin."""
    for _ in range(6):
        fail_login(anon.client, **{"X-Forwarded-For": "10.0.0.2"})
    admin = anon.client_from("10.0.0.2")
    assert admin.post("/auth/login", json={"password": PASSWORD}).status_code == 200


def test_per_client_threshold_comes_from_settings(make_env: EnvFactory) -> None:
    """D-15: login_max_failures is respected (2 instead of 5)."""
    env = make_env(login=False, login_max_failures=2)
    assert env.login("bad").status_code == 401
    assert env.login("bad").status_code == 401
    assert env.login("bad").status_code == 429


def test_global_threshold_comes_from_settings(make_env: EnvFactory) -> None:
    """D-15: login_max_failures_global is respected (3 instead of 50)."""
    env = make_env(login=False, login_max_failures_global=3)
    trip_global_cap(env, 3, prefix="10.2.0")
    assert login_from(env, "10.2.0.99") == 429


def test_throttle_gap_comes_from_settings(make_env: EnvFactory) -> None:
    """D-15: login_throttle_seconds is respected (2 instead of 5)."""
    env = make_env(login=False, login_max_failures_global=3, login_throttle_seconds=2)
    trip_global_cap(env, 3, prefix="10.2.0")
    env.clock.advance(seconds=2)
    assert login_from(env, "10.2.0.99") == 200


def test_lockout_duration_comes_from_settings(make_env: EnvFactory) -> None:
    """A9/D-15: login_lockout_minutes is respected."""
    env = make_env(login=False, login_lockout_minutes=2)
    for _ in range(5):
        env.login("bad")
    assert env.login(PASSWORD).status_code == 429
    env.clock.advance(minutes=3)
    assert env.login(PASSWORD).status_code == 200


# ---- trusted proxies (D-15 5) ---------------------------------------------------------


def fail_via(env: Env, proxy: str, forwarded: str | None) -> int:
    """A wrong-password login from peer ``proxy`` with an optional X-Forwarded-For header."""
    headers = {} if forwarded is None else {"X-Forwarded-For": forwarded}
    return fail_login(env.client_from(proxy), **headers)


def test_trusted_proxy_forwarded_address_is_the_client(make_env: EnvFactory) -> None:
    """D-15 (5b): counting uses the forwarded address; two addresses are two clients."""
    env = make_env(login=False, trusted_proxies=["10.0.0.5"])
    for _ in range(5):
        assert fail_via(env, "10.0.0.5", "203.0.113.9") == 401
    assert fail_via(env, "10.0.0.5", "203.0.113.9") == 429
    assert fail_via(env, "10.0.0.5", "203.0.113.10") == 401  # a different client


def test_the_proxy_itself_is_not_locked_by_its_users_failures(make_env: EnvFactory) -> None:
    """D-15 (5b): the admin behind the same proxy can still log in."""
    env = make_env(login=False, trusted_proxies=["10.0.0.5"])
    for _ in range(6):
        fail_via(env, "10.0.0.5", "203.0.113.9")
    admin = env.client_from("10.0.0.5")
    response = admin.post(
        "/auth/login", json={"password": PASSWORD}, headers={"X-Forwarded-For": "198.51.100.1"}
    )
    assert response.status_code == 200


def test_rightmost_untrusted_address_in_the_chain_is_used(make_env: EnvFactory) -> None:
    """D-15 (5c)."""
    env = make_env(login=False, trusted_proxies=["10.0.0.5", "10.0.0.6"])
    for _ in range(5):
        assert fail_via(env, "10.0.0.5", "1.1.1.1, 203.0.113.9") == 401
    # same right-most client, different left part and an extra trusted hop on the right
    assert fail_via(env, "10.0.0.5", "2.2.2.2, 203.0.113.9") == 429
    assert fail_via(env, "10.0.0.5", "203.0.113.9, 10.0.0.6") == 429
    assert fail_via(env, "10.0.0.5", "1.1.1.1, 203.0.113.10") == 401


def test_cidr_entries_in_trusted_proxies_match_peers(make_env: EnvFactory) -> None:
    """D-15 (5d): 10.0.0.0/8 trusts a peer like 10.1.2.3."""
    env = make_env(login=False, trusted_proxies=["10.0.0.0/8"])
    for _ in range(5):
        assert fail_via(env, "10.1.2.3", "203.0.113.9") == 401
    assert fail_via(env, "10.7.7.7", "203.0.113.9") == 429  # other proxy, same real client


def test_untrusted_peer_outside_the_cidr_gets_no_forwarding(make_env: EnvFactory) -> None:
    """D-15 (5a, 5d)."""
    env = make_env(login=False, trusted_proxies=["10.0.0.0/8"])
    for number in range(5):
        assert fail_via(env, "192.0.2.1", f"203.0.113.{number}") == 401
    assert fail_via(env, "192.0.2.1", "203.0.113.200") == 429


@pytest.mark.parametrize("bad", ["not-an-ip", "", "999.1.1.1", "1.1.1.1, garbage", "::::"])
def test_invalid_forwarded_value_falls_back_to_the_peer_address(
    make_env: EnvFactory, bad: str
) -> None:
    """D-15 (5e): no crash; counted against the proxy's own address."""
    env = make_env(login=False, trusted_proxies=["10.0.0.5"])
    for _ in range(5):
        assert fail_via(env, "10.0.0.5", bad) == 401
    assert fail_via(env, "10.0.0.5", None) == 429


def test_default_is_no_trusted_proxy(make_env: EnvFactory) -> None:
    """D-15 (5a)."""
    env = make_env(login=False)
    assert env.settings.trusted_proxies == []


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
