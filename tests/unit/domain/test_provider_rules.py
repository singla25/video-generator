"""RP-EST / RP-SET / RP-SEL / RP-CAP: estimate, setup, selectable and cap rules (AC2, AC3, AC5,
  AC7).

EXPECTED API (vidgen.domain.providers, all pure)
  MIN_MEASURED_RUNS = 3;  NOT_MEASURED_LABEL = "not measured yet"
  MeasuredRun(status: str, seconds: float)       one finished row this provider rendered
  Estimate(seconds_per_video, batch_seconds, batch_cost_usd)   frozen dataclass of floats
  estimate_for(provider, runs: Sequence[MeasuredRun], batch_rows: int) -> Estimate | None
      only status "COMPLETED" runs count; < MIN_MEASURED_RUNS -> None; seconds = median;
      batch_seconds = seconds * batch_rows; cost = batch_seconds * provider.rate_per_second
  SetupState(ready: bool, reason: str | None)
  setup_state(provider, *, env: Mapping[str, str], queue_alive: bool) -> SetupState
      missing or empty env var -> not ready, reason names it; no heartbeat -> "worker not running"
  remaining_credit(provider, spent: float) -> float | None     cap - spent, never below 0; None
    = no cap
  data_allowed(provider, data_class: DataClass) -> bool;  DataClass(StrEnum) REAL="real",
    DEMO="demo"
  Selectability(selectable: bool, code: str | None, reason: str | None)
  check_selectable(provider, *, setup: SetupState, data_class, estimate: Estimate | None, spent:
    float)
      codes: REFUSAL_NOT_READY="not_ready", REFUSAL_DATA_CLASS="data_class",
        REFUSAL_OVER_CREDIT="over_credit"
      checked in that order; the estimate may equal the remaining credit; no estimate never refuses
  row_worst_case_usd(provider, row_timeout_seconds: int) -> float        timeout * rate_per_second
  would_pass_cap(provider, spent, row_timeout_seconds) -> bool           spent + worst case > cap
  pause_reason(status: str, provider, data_class, spent, row_timeout_seconds) -> str | None
      only for "PAUSED": data class violation -> PAUSE_DATA_CLASS, cap -> PAUSE_SPEND_CAP
        ("spend cap reached")
"""

from __future__ import annotations

import pytest

from tests.fixtures.providers import MODAL_ENV, local_provider, remote_provider
from vidgen.domain.providers import (
    MIN_MEASURED_RUNS,
    NOT_MEASURED_LABEL,
    PAUSE_DATA_CLASS,
    PAUSE_SPEND_CAP,
    REFUSAL_DATA_CLASS,
    REFUSAL_NOT_READY,
    REFUSAL_OVER_CREDIT,
    DataClass,
    Estimate,
    MeasuredRun,
    SetupState,
    check_selectable,
    data_allowed,
    estimate_for,
    pause_reason,
    remaining_credit,
    row_worst_case_usd,
    setup_state,
    would_pass_cap,
)

READY = SetupState(ready=True, reason=None)
DONE = "COMPLETED"


def runs(*seconds: float, status: str = DONE) -> list[MeasuredRun]:
    return [MeasuredRun(status, s) for s in seconds]


# ---- estimates ------------------------------------------------------------------------


def test_the_minimum_number_of_measured_runs_is_three_and_the_label_is_fixed() -> None:
    """RP-EST-P0: Admin answer Q1."""
    assert MIN_MEASURED_RUNS == 3
    assert NOT_MEASURED_LABEL == "not measured yet"


def test_three_measured_runs_give_the_median_time_and_cost_is_time_times_rate() -> None:
    """RP-EST-P1."""
    estimate = estimate_for(remote_provider(rate_per_second=0.002), runs(10, 40, 20), 100)
    assert estimate == Estimate(seconds_per_video=20, batch_seconds=2000, batch_cost_usd=4.0)


def test_an_even_number_of_runs_uses_the_mean_of_the_middle_two() -> None:
    """RP-EST-E1."""
    estimate = estimate_for(local_provider(), runs(10, 20, 30, 50), 2)
    assert estimate is not None
    assert estimate.seconds_per_video == 25


@pytest.mark.parametrize("count", [0, 1, 2])
def test_fewer_than_three_runs_are_not_measured_yet(count: int) -> None:
    """RP-EST-N1 / N2: never guess from fewer rows."""
    assert estimate_for(remote_provider(), runs(*([12.0] * count)), 10) is None


def test_failed_and_cancelled_runs_do_not_count() -> None:
    """RP-EST-E2: two good runs plus failures are still 'not measured yet'."""
    mixed = runs(5, 5) + runs(900, status="FAILED") + runs(1, status="CANCELLED")
    assert estimate_for(remote_provider(), mixed, 10) is None
    assert estimate_for(remote_provider(), mixed + runs(5), 10) is not None


def test_a_local_provider_has_a_time_estimate_and_zero_cost() -> None:
    """RP-EST-E3: rate 0."""
    estimate = estimate_for(local_provider(), runs(8, 8, 8), 50)
    assert estimate == Estimate(seconds_per_video=8, batch_seconds=400, batch_cost_usd=0.0)


# ---- setup state ----------------------------------------------------------------------


def test_all_env_present_and_a_live_heartbeat_is_ready() -> None:
    """RP-SET-P1."""
    state = setup_state(remote_provider(), env=MODAL_ENV, queue_alive=True)
    assert state == SetupState(ready=True, reason=None)


def test_a_missing_env_var_means_needs_setup_and_names_the_variable() -> None:
    """RP-SET-N1."""
    env = {"MODAL_TOKEN_SECRET": "x"}
    state = setup_state(remote_provider(), env=env, queue_alive=True)
    assert not state.ready
    assert state.reason is not None
    assert "MODAL_TOKEN_ID" in state.reason
    assert "x" not in state.reason.replace("MODAL_TOKEN_ID", "")  # never echoes a value


def test_no_heartbeat_means_needs_setup_worker_not_running() -> None:
    """RP-SET-N2."""
    state = setup_state(remote_provider(), env=MODAL_ENV, queue_alive=False)
    assert not state.ready
    assert state.reason == "worker not running"


def test_an_env_var_that_is_present_but_empty_counts_as_missing() -> None:
    """RP-SET-E1."""
    env = {**MODAL_ENV, "MODAL_TOKEN_ID": ""}
    state = setup_state(remote_provider(), env=env, queue_alive=True)
    assert not state.ready
    assert "MODAL_TOKEN_ID" in (state.reason or "")


def test_a_provider_without_requirements_needs_only_a_worker() -> None:
    """RP-SET-E2."""
    assert setup_state(local_provider(), env={}, queue_alive=True).ready
    assert not setup_state(local_provider(), env={}, queue_alive=False).ready


# ---- selectable -----------------------------------------------------------------------

BIG = Estimate(seconds_per_video=100, batch_seconds=1000, batch_cost_usd=1.0)


def check(estimate: Estimate | None, spent: float = 0.0, **kw: object):  # type: ignore[no-untyped-def]
    args: dict[str, object] = {
        "setup": READY,
        "data_class": DataClass.DEMO,
        "estimate": estimate,
        "spent": spent,
    }
    args.update(kw)
    return check_selectable(remote_provider(), **args)  # type: ignore[arg-type]


def test_a_ready_provider_that_fits_data_class_and_credit_is_selectable() -> None:
    """RP-SEL-P1."""
    result = check(BIG)
    assert (result.selectable, result.code, result.reason) == (True, None, None)


def test_a_provider_that_is_not_ready_is_refused_with_its_reason() -> None:
    """RP-SEL-N1."""
    result = check(BIG, setup=SetupState(False, "worker not running"))
    assert (result.selectable, result.code) == (False, REFUSAL_NOT_READY)
    assert "worker not running" in (result.reason or "")


def test_a_demo_only_provider_is_refused_for_real_data() -> None:
    """RP-SEL-N2 (C5)."""
    result = check(BIG, data_class=DataClass.REAL)
    assert (result.selectable, result.code) == (False, REFUSAL_DATA_CLASS)
    assert data_allowed(local_provider(), DataClass.REAL)
    assert not data_allowed(remote_provider(), DataClass.REAL)
    assert data_allowed(remote_provider(), DataClass.DEMO)


def test_an_estimate_above_the_remaining_credit_is_refused() -> None:
    """RP-SEL-N3 (AC5): 5.0 cap, 4.5 spent, estimate 1.0."""
    result = check(BIG, spent=4.5)
    assert (result.selectable, result.code) == (False, REFUSAL_OVER_CREDIT)
    assert result.reason


def test_an_estimate_equal_to_the_remaining_credit_is_allowed() -> None:
    """RP-SEL-E1."""
    assert check(BIG, spent=4.0).selectable


def test_not_measured_yet_with_a_cap_can_be_picked() -> None:
    """RP-SEL-E2 (Q2 = yes): the cap still stops it at run time."""
    assert check(None, spent=2.0).selectable


def test_remaining_credit_is_cap_minus_spent_floored_at_zero_and_none_without_cap() -> None:
    """RP-SEL-E3."""
    assert remaining_credit(remote_provider(), 1.25) == 3.75
    assert remaining_credit(remote_provider(), 9.0) == 0.0
    assert remaining_credit(local_provider(), 100.0) is None


def test_a_provider_without_a_cap_is_never_over_credit() -> None:
    """RP-SEL-E4."""
    huge = Estimate(1.0, 1.0, 1_000_000.0)
    result = check_selectable(
        local_provider(), setup=READY, data_class=DataClass.REAL, estimate=huge, spent=5.0
    )
    assert result.selectable


# ---- spend cap ------------------------------------------------------------------------


def test_the_worst_case_of_a_row_is_its_time_limit_times_the_rate() -> None:
    """RP-CAP-P0."""
    assert row_worst_case_usd(remote_provider(rate_per_second=0.01), 5) == pytest.approx(0.05)
    assert row_worst_case_usd(local_provider(), 600) == 0.0


@pytest.mark.parametrize(
    ("spent", "expected"),
    [(0.0, False), (4.4, False), (4.5, False), (4.6, True), (5.0, True)],
)
def test_the_cap_is_passed_only_when_spent_plus_worst_case_is_above_it(
    spent: float, expected: bool
) -> None:
    """RP-CAP-P1 / E1: worst case 0.5, cap 5.0; exactly reaching the cap is allowed."""
    provider = remote_provider(rate_per_second=0.1)
    assert would_pass_cap(provider, spent, 5) is expected


def test_a_raised_cap_lets_the_batch_continue() -> None:
    """RP-CAP-E2: cap raised -> the same spend no longer passes it."""
    low = remote_provider(spend_cap_usd=5.0, rate_per_second=0.01)
    high = remote_provider(spend_cap_usd=8.0, rate_per_second=0.01)
    assert would_pass_cap(low, 4.99, 5)
    assert not would_pass_cap(high, 4.99, 5)


def test_a_provider_without_a_cap_never_passes_it() -> None:
    """RP-CAP-E3."""
    assert not would_pass_cap(local_provider(), 1_000_000.0, 600)


def test_the_pause_reason_names_the_cap_or_the_data_class_only_while_paused() -> None:
    """RP-CAP-P2."""
    provider = remote_provider(rate_per_second=0.01)
    cap_args = (provider, DataClass.DEMO, 4.99, 5)
    assert pause_reason("PAUSED", *cap_args) == PAUSE_SPEND_CAP == "spend cap reached"
    assert pause_reason("RUNNING", *cap_args) is None
    assert pause_reason("PAUSED", provider, DataClass.DEMO, 0.0, 5) is None
    assert pause_reason("PAUSED", provider, DataClass.REAL, 0.0, 5) == PAUSE_DATA_CLASS
