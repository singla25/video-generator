"""Login protection (D-15, D-17): per-client lockout plus a global throttle.

The decisions are pure functions over small state values with an injected time. The state
itself lives behind ``LoginStateStore`` (Postgres in production), so every API instance and
every restart sees the same counters. Only login attempts are limited; sessions are untouched.

Counting uses a fixed window that starts at the first failure: once the window has passed, the
next failure starts a new one.
"""

from __future__ import annotations

import math
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

GLOBAL_KEY = "*"  # sentinel client key of the global row; never a valid IP address


@dataclass(frozen=True)
class LoginRules:
    """Thresholds, all from settings."""

    max_failures: int
    max_failures_global: int
    window: timedelta
    lockout: timedelta
    throttle_gap: timedelta


@dataclass(frozen=True)
class AttemptState:
    """Failure counter of one client, or of everybody (the global row).

    ``locked_until`` is the lock end for a client and the throttle end for the global row.
    ``last_allowed_at`` is only used by the global row (the 1-per-gap rule).
    """

    window_started_at: datetime | None = None
    failure_count: int = 0
    locked_until: datetime | None = None
    last_allowed_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        """True when nothing needs to be remembered."""
        return self.failure_count == 0 and self.locked_until is None


class LoginTransaction(Protocol):
    """Both states for one attempt, loaded under a lock and saved atomically."""

    @property
    def client(self) -> AttemptState:
        """The client's state."""
        ...

    @property
    def total(self) -> AttemptState:
        """The global state."""
        ...

    def save(self, client: AttemptState, total: AttemptState, *, prune_before: datetime) -> None:
        """Store both states and delete stale rows older than ``prune_before``."""
        ...


class LoginStateStore(Protocol):
    """Shared storage for login state. Transactions must serialise concurrent callers."""

    def transaction(self, client_key: str) -> AbstractContextManager[LoginTransaction]:
        """Lock and load the client's and the global state; commit on a clean exit."""
        ...


def _seconds_left(until: datetime, now: datetime) -> int:
    """Whole seconds until ``until`` (rounded up, at least 1)."""
    return max(1, math.ceil((until - now).total_seconds()))


def check_attempt(
    client: AttemptState, total: AttemptState, now: datetime, rules: LoginRules
) -> tuple[int | None, AttemptState]:
    """Decide whether an attempt may be checked.

    Returns (seconds to wait or None, new global state). An allowed attempt is remembered as
    the last one, which is what spaces attempts out during a throttle.
    """
    if client.locked_until is not None and now < client.locked_until:
        return _seconds_left(client.locked_until, now), total
    if total.locked_until is not None and now < total.locked_until and total.last_allowed_at:
        gap_ends = total.last_allowed_at + rules.throttle_gap
        if now < gap_ends:
            return _seconds_left(gap_ends, now), total
    return None, replace(total, last_allowed_at=now)


def _count_failure(state: AttemptState, now: datetime, window: timedelta) -> AttemptState:
    """Add one failure, starting a new window if the old one has passed."""
    started = state.window_started_at
    if started is None or now - started >= window:
        return replace(state, window_started_at=now, failure_count=1)
    return replace(state, failure_count=state.failure_count + 1)


def after_failure(
    client: AttemptState, total: AttemptState, now: datetime, rules: LoginRules
) -> tuple[AttemptState, AttemptState, bool]:
    """Apply a wrong password. Returns (client, global, True if this started a throttle)."""
    counted = _count_failure(client, now, rules.window)
    if counted.failure_count >= rules.max_failures:
        counted = replace(counted, failure_count=0, locked_until=now + rules.lockout)
    throttled_already = total.locked_until is not None and now < total.locked_until
    # While a throttle is active nothing more is counted and no second alert is raised.
    summed = total if throttled_already else _count_failure(total, now, rules.window)
    crossed = not throttled_already and summed.failure_count >= rules.max_failures_global
    if crossed:
        summed = replace(summed, failure_count=0, locked_until=now + rules.lockout)
    return counted, summed, crossed


class LoginGuard:
    """Applies the rules to the shared state, one locked transaction per call."""

    def __init__(self, rules: LoginRules, store: LoginStateStore) -> None:
        self._rules = rules
        self._store = store

    def begin_attempt(self, client: str, now: datetime) -> int | None:
        """Return None if the attempt may be checked, else the seconds to wait (Retry-After)."""
        with self._store.transaction(client) as tx:
            wait, total = check_attempt(tx.client, tx.total, now, self._rules)
            tx.save(tx.client, total, prune_before=now - self._rules.window)
            return wait

    def record_failure(self, client: str, now: datetime) -> bool:
        """Count a wrong password. Returns True when this failure started a global throttle."""
        with self._store.transaction(client) as tx:
            new_client, total, started = after_failure(tx.client, tx.total, now, self._rules)
            tx.save(new_client, total, prune_before=now - self._rules.window)
            return started

    def record_success(self, client: str, now: datetime) -> None:
        """Forget this client's earlier failures."""
        with self._store.transaction(client) as tx:
            tx.save(AttemptState(), tx.total, prune_before=now - self._rules.window)
