"""RP-REC: provider records and the registry are validated (AC1). Pure domain, no I/O.

EXPECTED API (vidgen.domain.providers)
  ProviderKind(StrEnum): LOCAL="local", REMOTE_FUNCTION="remote_function",
    REMOTE_WORKER="remote_worker"
  DataRule(StrEnum): REAL_ALLOWED="real_allowed", DEMO_ONLY="demo_only"
  Provider(frozen dataclass; keywords): id, name, kind, queue, ai_mode, data_rule,
      spend_cap_usd: float | None = None, rate_per_second: float = 0.0, requires_env: tuple[str,
        ...] = ()
      raises InvalidProviderError (a ValueError with .provider_id, str() names the id) when invalid
  ProviderRegistry(providers: Sequence[Provider]): .providers (tuple), .default (first),
    .get(id) -> Provider | None,
      .for_batch(provider_id: str | None) -> Provider (None = default; unknown ->
        UnknownProviderError, a LookupError)
      raises InvalidProviderError on an empty list, a duplicate id or a duplicate queue
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.fixtures.providers import local_provider, remote_provider
from vidgen.domain.providers import (
    DataRule,
    InvalidProviderError,
    Provider,
    ProviderKind,
    ProviderRegistry,
    UnknownProviderError,
)

# ---- positive -------------------------------------------------------------------------


def test_a_local_provider_without_cap_is_valid() -> None:
    """RP-REC-P1: local = real data allowed, no cap, cost 0."""
    provider = local_provider()
    assert provider.spend_cap_usd is None
    assert provider.rate_per_second == 0.0
    assert provider.data_rule is DataRule.REAL_ALLOWED


@pytest.mark.parametrize("kind", [ProviderKind.REMOTE_FUNCTION, ProviderKind.REMOTE_WORKER])
def test_a_remote_provider_that_is_demo_only_with_a_cap_is_valid(kind: ProviderKind) -> None:
    """RP-REC-P2."""
    provider = remote_provider(kind=kind)
    assert provider.spend_cap_usd == 5.0
    assert provider.data_rule is DataRule.DEMO_ONLY


def test_the_registry_finds_providers_and_the_first_one_is_the_default() -> None:
    """RP-REC-P3: a batch without a provider id (old batch) uses the default provider."""
    local, remote = local_provider(), remote_provider()
    registry = ProviderRegistry([local, remote])
    assert registry.providers == (local, remote)
    assert registry.default == local
    assert registry.get("modal-demo") == remote
    assert registry.get("nope") is None
    assert registry.for_batch(None) == local
    assert registry.for_batch("modal-demo") == remote


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"kind": "teleporter"}, "kind"),
        ({"data_rule": DataRule.REAL_ALLOWED}, "real_allowed"),
        ({"spend_cap_usd": None}, "cap"),
        ({"spend_cap_usd": -1.0}, "cap"),
        ({"rate_per_second": -0.5}, "rate"),
        ({"id": "   "}, "id"),
    ],
)
def test_an_invalid_remote_provider_is_refused_naming_the_entry(
    overrides: dict[str, Any], fragment: str
) -> None:
    """RP-REC-N1: unknown kind, real_allowed on a remote kind, no cap on a paid kind, bad
    numbers."""
    with pytest.raises(InvalidProviderError) as raised:
        remote_provider(**overrides)
    assert fragment in str(raised.value)
    if overrides.get("id") is None:
        assert "modal-demo" in str(raised.value)


def test_a_remote_worker_with_real_allowed_is_refused() -> None:
    """RP-REC-N2: Q3 = no; remote kinds never take real data (no override exists)."""
    with pytest.raises(InvalidProviderError, match="modal-demo"):
        remote_provider(kind=ProviderKind.REMOTE_WORKER, data_rule=DataRule.REAL_ALLOWED)


def test_a_duplicate_id_is_refused_naming_it() -> None:
    """RP-REC-N3."""
    other = local_provider(queue="vidgen.other")
    with pytest.raises(InvalidProviderError, match="local-mac"):
        ProviderRegistry([local_provider(), other])


def test_a_duplicate_queue_is_refused_naming_the_providers() -> None:
    """RP-REC-N4: two providers on one queue would steal each other's jobs."""
    second = local_provider(id="local-two")
    with pytest.raises(InvalidProviderError, match="local-two"):
        ProviderRegistry([local_provider(), second])


def test_an_unknown_provider_id_for_a_batch_is_an_error() -> None:
    """RP-REC-N5."""
    with pytest.raises(UnknownProviderError):
        ProviderRegistry([local_provider()]).for_batch("ghost")


# ---- edge -----------------------------------------------------------------------------


def test_an_empty_registry_is_refused() -> None:
    """RP-REC-E1."""
    with pytest.raises(InvalidProviderError):
        ProviderRegistry([])


def test_a_local_provider_may_have_a_cap_and_a_unicode_name() -> None:
    """RP-REC-E2."""
    provider = local_provider(name="मेरा Mac 🍎", spend_cap_usd=1.0)
    assert provider.name == "मेरा Mac 🍎"
    assert isinstance(provider, Provider)
