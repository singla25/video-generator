"""Render providers: records, validation and the estimate, selectable and spend-cap rules.

Pure Python (ADR-013 amendment A1). No I/O: the registry file, the heartbeats and the database
are read by adapters and handed in as plain values.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

MIN_MEASURED_RUNS = 3  # Admin answer Q1: an estimate needs this many measured rows
NOT_MEASURED_LABEL = "not measured yet"
COMPLETED = "COMPLETED"
PAUSED = "PAUSED"
USD_DIGITS = 6  # money is stored with six decimals; compare at that precision
SECONDS_PER_HOUR = 3600
AI_MODES = ("fake", "local", "modal")

REFUSAL_NOT_READY = "not_ready"
REFUSAL_DATA_CLASS = "data_class"
REFUSAL_OVER_CREDIT = "over_credit"
PAUSE_SPEND_CAP = "spend cap reached"
PAUSE_DATA_CLASS = "provider not allowed for this data class"
WORKER_NOT_RUNNING = "worker not running"


class ProviderKind(StrEnum):
    """How jobs reach the hardware."""

    LOCAL = "local"
    REMOTE_FUNCTION = "remote_function"
    REMOTE_WORKER = "remote_worker"


class DataRule(StrEnum):
    """What data a provider may receive (C5)."""

    REAL_ALLOWED = "real_allowed"
    DEMO_ONLY = "demo_only"


class DataClass(StrEnum):
    """What a batch contains, declared at upload."""

    REAL = "real"
    DEMO = "demo"


class InvalidProviderError(ValueError):
    """A provider or the registry is not valid; the text names the entry, never a value."""

    def __init__(self, message: str, provider_id: str | None = None) -> None:
        self.provider_id = provider_id
        super().__init__(message)


class UnknownProviderError(LookupError):
    """No provider with this id is registered."""


def _enum(kind: type[StrEnum], value: Any, provider_id: str, label: str) -> Any:
    try:
        return kind(value)
    except ValueError:
        raise InvalidProviderError(
            f"provider '{provider_id}': unknown {label}", provider_id
        ) from None


def _refuse(provider_id: str, problem: str) -> InvalidProviderError:
    return InvalidProviderError(f"provider '{provider_id}': {problem}", provider_id)


@dataclass(frozen=True)
class Provider:
    """One render provider: what it is, what data it may take and how much it may spend."""

    id: str
    name: str
    kind: ProviderKind
    queue: str
    ai_mode: str
    data_rule: DataRule
    spend_cap_usd: float | None = None
    rate_per_second: float = 0.0
    requires_env: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate (and coerce enum strings); raises InvalidProviderError naming the entry."""
        pid = self.id
        kind = _enum(ProviderKind, self.kind, pid, "kind")
        rule = _enum(DataRule, self.data_rule, pid, "data_rule")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "data_rule", rule)
        object.__setattr__(self, "requires_env", tuple(self.requires_env))
        if not self.id.strip():
            raise _refuse(pid, "id must not be blank")
        if not self.queue.strip():
            raise _refuse(pid, "queue must not be blank")
        if self.ai_mode not in AI_MODES:
            raise _refuse(pid, "unknown ai_mode")
        if self.spend_cap_usd is not None and self.spend_cap_usd < 0:
            raise _refuse(pid, "spend cap (spend_cap_usd) must not be negative")
        if self.rate_per_second < 0:
            raise _refuse(pid, "rate must not be negative")
        if kind is not ProviderKind.LOCAL:
            if rule is DataRule.REAL_ALLOWED:
                raise _refuse(pid, "a remote provider cannot be real_allowed (C5)")
            if self.spend_cap_usd is None:
                raise _refuse(pid, "a remote provider needs a spend cap (spend_cap_usd)")


class ProviderRegistry:
    """The registered providers; the first one is the default for batches without a choice."""

    def __init__(self, providers: Sequence[Provider]) -> None:
        if not providers:
            raise InvalidProviderError("no providers are defined")
        ids: dict[str, Provider] = {}
        queues: dict[str, Provider] = {}
        for provider in providers:
            if provider.id in ids:
                raise _refuse(provider.id, "duplicate id")
            other = queues.get(provider.queue)
            if other is not None:
                raise _refuse(provider.id, f"queue is already used by provider '{other.id}'")
            ids[provider.id], queues[provider.queue] = provider, provider
        self.providers: tuple[Provider, ...] = tuple(providers)
        self._by_id = ids

    @property
    def default(self) -> Provider:
        """The provider used by batches that never chose one."""
        return self.providers[0]

    def get(self, provider_id: str) -> Provider | None:
        """The provider with this id, or None."""
        return self._by_id.get(provider_id)

    def for_batch(self, provider_id: str | None) -> Provider:
        """The batch's provider; None means the default, an unknown id is an error."""
        if provider_id is None:
            return self.default
        found = self._by_id.get(provider_id)
        if found is None:
            raise UnknownProviderError(provider_id)
        return found

    def is_default(self, provider: Provider) -> bool:
        """True for the default provider (it also owns the batches without a provider id)."""
        return provider.id == self.default.id


# ---- estimates -------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasuredRun:
    """One finished row a provider rendered."""

    status: str
    seconds: float


@dataclass(frozen=True)
class Estimate:
    """Time and cost of a batch, from measured runs only."""

    seconds_per_video: float
    batch_seconds: float
    batch_cost_usd: float


def estimate_for(
    provider: Provider, runs: Sequence[MeasuredRun], batch_rows: int
) -> Estimate | None:
    """Median-based estimate; None ("not measured yet") with fewer than MIN_MEASURED_RUNS."""
    seconds = [run.seconds for run in runs if run.status == COMPLETED]
    if len(seconds) < MIN_MEASURED_RUNS:
        return None
    per_video = float(statistics.median(seconds))
    batch_seconds = per_video * batch_rows
    return Estimate(per_video, batch_seconds, batch_seconds * provider.rate_per_second)


# ---- setup state -----------------------------------------------------------------------


@dataclass(frozen=True)
class SetupState:
    """Whether a provider can take work now, and why not."""

    ready: bool
    reason: str | None


def setup_state(provider: Provider, *, env: Mapping[str, str], queue_alive: bool) -> SetupState:
    """Ready only with every required variable set (non-empty) and a live worker heartbeat."""
    missing = [name for name in provider.requires_env if not env.get(name)]
    if missing:
        return SetupState(False, f"{', '.join(missing)} missing")
    if not queue_alive:
        return SetupState(False, WORKER_NOT_RUNNING)
    return SetupState(True, None)


# ---- credit, data class and selectability ----------------------------------------------


def remaining_credit(provider: Provider, spent: float) -> float | None:
    """Cap minus spent, never below zero; None without a cap."""
    if provider.spend_cap_usd is None:
        return None
    return max(0.0, provider.spend_cap_usd - spent)


def data_allowed(provider: Provider, data_class: DataClass) -> bool:
    """C5: a demo-only provider never takes real data."""
    return data_class is DataClass.DEMO or provider.data_rule is DataRule.REAL_ALLOWED


@dataclass(frozen=True)
class Selectability:
    """Whether the Admin may pick a provider, with a code and reason when not."""

    selectable: bool
    code: str | None = None
    reason: str | None = None


def check_selectable(
    provider: Provider,
    *,
    setup: SetupState,
    data_class: DataClass,
    estimate: Estimate | None,
    spent: float,
) -> Selectability:
    """Not ready, then data class, then credit; no estimate never refuses (Q2)."""
    if not setup.ready:
        return Selectability(False, REFUSAL_NOT_READY, f"Needs setup: {setup.reason}")
    if not data_allowed(provider, data_class):
        return Selectability(
            False, REFUSAL_DATA_CLASS, "This provider cannot take real data (demo data only)."
        )
    remaining = remaining_credit(provider, spent)
    if (
        estimate is not None
        and remaining is not None
        and round(estimate.batch_cost_usd, USD_DIGITS) > round(remaining, USD_DIGITS)
    ):
        return Selectability(
            False, REFUSAL_OVER_CREDIT, "The estimated cost is above the remaining credit."
        )
    return Selectability(True)


# ---- spend cap -------------------------------------------------------------------------


def row_worst_case_usd(provider: Provider, row_timeout_seconds: int) -> float:
    """The most one row can cost: its time limit at the provider's rate."""
    return row_timeout_seconds * provider.rate_per_second


def would_pass_cap(provider: Provider, spent: float, row_timeout_seconds: int) -> bool:
    """True when ``spent`` plus one row's worst case is above the cap (equal is allowed)."""
    if provider.spend_cap_usd is None:
        return False
    total = spent + row_worst_case_usd(provider, row_timeout_seconds)
    return round(total, USD_DIGITS) > round(provider.spend_cap_usd, USD_DIGITS)


def pause_reason(
    status: str,
    provider: Provider,
    data_class: DataClass,
    spent: float,
    row_timeout_seconds: int,
) -> str | None:
    """Why a PAUSED batch is paused by the provider rules; None for any other state."""
    if status != PAUSED:
        return None
    if not data_allowed(provider, data_class):
        return PAUSE_DATA_CLASS
    if would_pass_cap(provider, spent, row_timeout_seconds):
        return PAUSE_SPEND_CAP
    return None
