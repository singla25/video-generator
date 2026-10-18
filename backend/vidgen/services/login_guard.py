"""Login protection (D-15): per-client lockout plus a global throttle.

Pure decision logic with an injected time, so it is fully testable. State is kept in this
process; a multi-instance deployment would move it to Redis (the interface would not change).
Only login attempts are limited; existing sessions are never touched.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class LoginRules:
    """Thresholds, all from settings."""

    max_failures: int
    max_failures_global: int
    window: timedelta
    lockout: timedelta
    throttle_gap: timedelta


def _seconds_left(until: datetime, now: datetime) -> int:
    """Whole seconds until ``until`` (rounded up, at least 1)."""
    return max(1, math.ceil((until - now).total_seconds()))


class LoginGuard:
    """Decides whether a login attempt may be evaluated and tracks failures."""

    def __init__(self, rules: LoginRules) -> None:
        self._rules = rules
        self._lock = threading.Lock()
        self._failures: dict[str, deque[datetime]] = {}
        self._locked_until: dict[str, datetime] = {}
        self._global_failures: deque[datetime] = deque()
        self._throttled_until: datetime | None = None
        self._last_evaluated: datetime | None = None

    def begin_attempt(self, client: str, now: datetime) -> int | None:
        """Return None if the attempt may be checked, else the seconds to wait (Retry-After)."""
        with self._lock:
            locked_until = self._locked_until.get(client)
            if locked_until is not None:
                if now < locked_until:
                    return _seconds_left(locked_until, now)
                del self._locked_until[client]
            if self._throttled_until is not None and now < self._throttled_until:
                gap_ends = (self._last_evaluated or now) + self._rules.throttle_gap
                if self._last_evaluated is not None and now < gap_ends:
                    return _seconds_left(gap_ends, now)
            self._last_evaluated = now
            return None

    def record_failure(self, client: str, now: datetime) -> bool:
        """Count a wrong password. Returns True when this failure started a global throttle."""
        with self._lock:
            recent = self._failures.setdefault(client, deque())
            self._append(recent, now)
            if len(recent) >= self._rules.max_failures:
                self._locked_until[client] = now + self._rules.lockout
                del self._failures[client]
            return self._count_global(now)

    def record_success(self, client: str) -> None:
        """Forget this client's earlier failures."""
        with self._lock:
            self._failures.pop(client, None)

    def _append(self, queue: deque[datetime], now: datetime) -> None:
        """Add ``now`` and drop entries older than the window."""
        queue.append(now)
        cutoff = now - self._rules.window
        while queue and queue[0] <= cutoff:
            queue.popleft()

    def _count_global(self, now: datetime) -> bool:
        """Add a global failure; start the throttle (once per window) at the cap."""
        self._append(self._global_failures, now)
        throttle_active = self._throttled_until is not None and now < self._throttled_until
        if throttle_active or len(self._global_failures) < self._rules.max_failures_global:
            return False
        self._throttled_until = now + self._rules.lockout
        self._global_failures.clear()
        return True
