"""AC5: registry fallback and the existing chooser / C5 / spend-cap rules with ai_mode modal.

No database: the pure rules (domain) and the worker guard are run with a modal registry.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.fixtures.providers import FakeQueueHeartbeats
from vidgen.domain.providers import (
    REFUSAL_DATA_CLASS,
    REFUSAL_NOT_READY,
    DataClass,
    DataRule,
    Provider,
    ProviderKind,
    check_selectable,
    setup_state,
)
from vidgen.infrastructure.provider_registry import load_registry
from vidgen.services.provider_guard import ProviderGuard

QUEUE = "vidgen"
TOKENS = {"MODAL_TOKEN_ID": "demo-id", "MODAL_TOKEN_SECRET": "demo-secret"}
TIMEOUT = 600


def registry() -> Any:
    return load_registry(None, ai_mode="modal", queue_name=QUEUE)


@pytest.fixture
def provider() -> Provider:
    return registry().default  # type: ignore[no-any-return]


def selectable(p: Provider, data_class: DataClass, *, env: Any = TOKENS, alive: bool = True) -> Any:
    return check_selectable(
        p,
        setup=setup_state(p, env=env, queue_alive=alive),
        data_class=data_class,
        estimate=None,
        spent=0.0,
    )


def guard() -> ProviderGuard:
    return ProviderGuard(registry(), row_timeout_seconds=TIMEOUT)


def test_the_fallback_provider_in_modal_mode_is_a_demo_only_remote_function(
    provider: Provider,
) -> None:
    assert provider.kind is ProviderKind.REMOTE_FUNCTION
    assert provider.data_rule is DataRule.DEMO_ONLY
    assert provider.ai_mode == "modal"
    assert provider.queue == QUEUE


def test_the_fallback_requires_the_two_token_names_only(provider: Provider) -> None:
    assert set(provider.requires_env) == {"MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"}


def test_the_fallback_has_a_positive_cap_and_rate_so_the_spend_cap_can_pause(
    provider: Provider,
) -> None:
    assert provider.spend_cap_usd is not None and provider.spend_cap_usd > 0
    assert provider.rate_per_second > 0


@pytest.mark.parametrize("mode", ["fake", "local"])
def test_fake_and_local_fallbacks_are_unchanged(mode: str) -> None:
    p = load_registry(None, ai_mode=mode, queue_name=QUEUE).default
    assert (p.kind, p.data_rule, p.requires_env) == (
        ProviderKind.LOCAL,
        DataRule.REAL_ALLOWED,
        (),
    )


@pytest.mark.parametrize("missing", ["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"])
def test_not_ready_when_a_token_name_is_missing_or_empty(provider: Provider, missing: str) -> None:
    for env in ({k: v for k, v in TOKENS.items() if k != missing}, {**TOKENS, missing: ""}):
        state = setup_state(provider, env=env, queue_alive=True)
        assert not state.ready and missing in (state.reason or "")


def test_not_ready_without_a_live_worker(provider: Provider) -> None:
    assert not setup_state(provider, env=TOKENS, queue_alive=False).ready


def test_ready_with_both_tokens_and_a_worker_beat_on_its_queue(provider: Provider) -> None:
    beats = FakeQueueHeartbeats({provider.queue})
    assert setup_state(provider, env=TOKENS, queue_alive=beats.is_alive(provider.queue)).ready


def test_a_batch_with_real_data_is_refused_even_when_ready(provider: Provider) -> None:
    result = selectable(provider, DataClass.REAL)
    assert not result.selectable and result.code == REFUSAL_DATA_CLASS


def test_a_demo_batch_is_allowed_once_the_provider_is_ready(provider: Provider) -> None:
    assert selectable(provider, DataClass.DEMO).selectable


def test_a_demo_batch_is_refused_while_not_ready(provider: Provider) -> None:
    result = selectable(provider, DataClass.DEMO, env={})
    assert not result.selectable and result.code == REFUSAL_NOT_READY


def test_the_worker_guard_pauses_a_real_batch_on_the_modal_provider() -> None:
    reason = guard().pause_reason(None, "real", lambda *_: 0.0)
    assert reason is not None and "data class" in reason


def test_the_worker_guard_lets_a_demo_batch_start_with_credit_left() -> None:
    assert guard().pause_reason(None, "demo", lambda *_: 0.0) is None


def test_the_spend_cap_pauses_when_the_cap_is_already_reached(provider: Provider) -> None:
    assert provider.spend_cap_usd is not None
    reason = guard().pause_reason(None, "demo", lambda *_: provider.spend_cap_usd or 0.0)
    assert reason == "spend cap reached"


def test_the_cost_of_a_row_is_its_seconds_at_the_provider_rate(provider: Provider) -> None:
    assert guard().cost_usd(None, 10.0) == pytest.approx(10.0 * provider.rate_per_second)
