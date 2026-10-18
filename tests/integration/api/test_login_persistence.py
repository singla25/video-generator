"""Login protection state lives in the database, not in the process (CLAUDE.md section 4).

Each test builds several app instances on the same test database, as two API servers or a
restarted server would be. Everything is checked through the HTTP API only.
"""

from __future__ import annotations

from tests.integration.api.conftest import PASSWORD, Env, EnvFactory

ATTACKER = "10.7.0.1"


def fail(env: Env, address: str) -> int:
    """A wrong-password login from ``address`` against this instance."""
    client = env.client_from(address)
    return client.post("/auth/login", json={"password": "bad"}).status_code


def good(env: Env, address: str) -> int:
    """A correct login from ``address`` against this instance."""
    client = env.client_from(address)
    return client.post("/auth/login", json={"password": PASSWORD}).status_code


def trip_global_cap(env: Env) -> None:
    """50 failures from 50 addresses."""
    for number in range(50):
        assert fail(env, f"10.1.0.{number + 1}") == 401


# ---- (a) per-client failures are shared ------------------------------------------------


def test_failures_counted_on_one_instance_lock_the_client_on_another(
    make_env: EnvFactory,
) -> None:
    """Per-client count is shared: 3 failures on A + 2 on B lock the client everywhere."""
    node_a = make_env(login=False)
    node_b = node_a.new_instance()
    for _ in range(3):
        assert fail(node_a, ATTACKER) == 401
    for _ in range(2):
        assert fail(node_b, ATTACKER) == 401
    assert fail(node_a, ATTACKER) == 429
    assert fail(node_b, ATTACKER) == 429
    assert good(node_b, ATTACKER) == 429


def test_a_client_locked_on_one_instance_does_not_lock_others_on_the_other(
    make_env: EnvFactory,
) -> None:
    """The admin at another address can still log in on either instance."""
    node_a = make_env(login=False)
    node_b = node_a.new_instance()
    for _ in range(6):
        fail(node_a, ATTACKER)
    assert good(node_b, "10.0.0.2") == 200


# ---- (b) the global throttle is shared -------------------------------------------------


def test_global_throttle_started_on_a_applies_on_b(make_env: EnvFactory) -> None:
    """D-15: 50 failures on A throttle logins on B, and the gap rule holds there too."""
    node_a = make_env(login=False)
    node_b = node_a.new_instance()
    trip_global_cap(node_a)
    assert good(node_b, "10.9.9.9") == 429
    node_a.clock.advance(seconds=5)
    assert good(node_b, "10.9.9.9") == 200
    assert good(node_a, "10.9.9.10") == 429  # B's success used the allowed attempt


def test_failures_spread_over_both_instances_add_up_to_the_global_cap(
    make_env: EnvFactory,
) -> None:
    """25 failures on each instance reach the cap together."""
    node_a = make_env(login=False)
    node_b = node_a.new_instance()
    for number in range(25):
        assert fail(node_a, f"10.1.0.{number + 1}") == 401
        assert fail(node_b, f"10.2.0.{number + 1}") == 401
    assert good(node_a, "10.9.9.9") == 429


def test_one_alert_per_window_even_with_two_instances(make_env: EnvFactory) -> None:
    """D-15 (4): the alert is written once, not once per instance."""
    admin = make_env()
    node_b = admin.new_instance()
    for number in range(25):
        fail(admin, f"10.1.0.{number + 1}")
        fail(node_b, f"10.2.0.{number + 1}")
    entries = admin.client.get("/audit", params={"action": "SECURITY_LOGIN_THROTTLED"}).json()
    assert len(entries["entries"]) == 1


# ---- (c) state survives a restart ------------------------------------------------------


def test_per_client_lock_survives_a_restart(make_env: EnvFactory) -> None:
    """A new app instance after the old one is discarded still knows the failures."""
    first = make_env(login=False)
    for _ in range(5):
        assert fail(first, ATTACKER) == 401
    restarted = first.new_instance()
    del first
    assert fail(restarted, ATTACKER) == 429
    assert good(restarted, ATTACKER) == 429


def test_four_failures_survive_a_restart_and_the_fifth_still_counts(
    make_env: EnvFactory,
) -> None:
    """Boundary across a restart."""
    first = make_env(login=False)
    for _ in range(4):
        fail(first, ATTACKER)
    restarted = first.new_instance()
    assert fail(restarted, ATTACKER) == 401  # the 5th failure
    assert fail(restarted, ATTACKER) == 429


def test_global_throttle_survives_a_restart(make_env: EnvFactory) -> None:
    """D-15: the throttle window is not reset by restarting the server."""
    first = make_env(login=False)
    trip_global_cap(first)
    restarted = first.new_instance()
    del first
    assert good(restarted, "10.9.9.9") == 429
    restarted.clock.advance(seconds=5)
    assert good(restarted, "10.9.9.9") == 200


def test_lock_ends_on_schedule_after_a_restart(make_env: EnvFactory) -> None:
    """The 15 minute lock is measured with timestamps, not in-process timers."""
    first = make_env(login=False)
    for _ in range(5):
        fail(first, ATTACKER)
    restarted = first.new_instance()
    restarted.clock.advance(minutes=14)
    assert good(restarted, ATTACKER) == 429
    restarted.clock.advance(minutes=2)
    assert good(restarted, ATTACKER) == 200


def test_old_failures_age_out_even_across_instances(make_env: EnvFactory) -> None:
    """3 failures on A, 16 minutes later 3 on B: no lock."""
    node_a = make_env(login=False)
    node_b = node_a.new_instance()
    for _ in range(3):
        fail(node_a, ATTACKER)
    node_a.clock.advance(minutes=16)
    for _ in range(3):
        assert fail(node_b, ATTACKER) == 401
    assert good(node_b, ATTACKER) == 200


def test_sessions_issued_by_one_instance_work_on_another(make_env: EnvFactory) -> None:
    """Stateless API: the signed cookie is valid on every instance."""
    node_a = make_env()
    node_b = node_a.new_instance()
    node_b.client.cookies.set("vidgen_session", node_a.client.cookies["vidgen_session"])
    assert node_b.client.get("/templates").status_code == 200
