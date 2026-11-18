"""Worker-side provider rules: C5 and the spend cap, checked before each row (AC7, AC8).

The API checks the same rules, but the worker does not trust it: a demo-only provider never
renders a real batch, and a row that could take the provider past its cap is not started.
"""

from __future__ import annotations

import logging

from vidgen.domain.providers import (
    DataClass,
    Provider,
    ProviderRegistry,
    UnknownProviderError,
    pause_reason,
)
from vidgen.ports.rows import SpendLookup

logger = logging.getLogger(__name__)
PAUSED = "PAUSED"


class ProviderGuard:
    """Decides, per row, whether the batch's provider may start it."""

    def __init__(self, registry: ProviderRegistry, *, row_timeout_seconds: int) -> None:
        self._registry = registry
        self._timeout = row_timeout_seconds

    def pause_reason(
        self, provider_id: str | None, data_class: str, spent: SpendLookup
    ) -> str | None:
        """The reason to pause the batch before the next row, or None to go ahead."""
        provider = self._provider(provider_id)
        total = 0.0
        if provider.spend_cap_usd is not None:  # no cap: skip the query
            total = spent(provider.id, self._registry.is_default(provider))
        return pause_reason(PAUSED, provider, DataClass(data_class), total, self._timeout)

    def cost_usd(self, provider_id: str | None, seconds: float) -> float:
        """Measured cost of a row: its render time at the provider's rate."""
        return seconds * self._provider(provider_id).rate_per_second

    def _provider(self, provider_id: str | None) -> Provider:
        """The batch's provider; a retired id falls back to the default (logged)."""
        try:
            return self._registry.for_batch(provider_id)
        except UnknownProviderError:
            logger.warning("batch provider is not registered; using the default")
            return self._registry.default
