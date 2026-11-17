"""The render plan chooser: which providers a batch may use, and choosing one (AC3-AC6, AC8).

Everything is read from the database and the registry; the rules themselves live in
``vidgen.domain.providers``. A refusal raises ``ProviderChoiceError`` before anything changes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from vidgen.domain.providers import (
    REFUSAL_DATA_CLASS,
    REFUSAL_NOT_READY,
    DataClass,
    Estimate,
    Provider,
    Selectability,
    SetupState,
    UnknownProviderError,
    check_selectable,
    estimate_for,
    remaining_credit,
    setup_state,
)
from vidgen.domain.status import BatchState
from vidgen.ports import UnitOfWork
from vidgen.ports.batches import BatchRecord
from vidgen.services.batch_support import (
    BatchContext,
    audit,
    enqueue_rows,
    load_batch,
)
from vidgen.services.errors import ProviderChoiceError, StateConflictError

MEASURED_WINDOW = 200  # the latest completed rows used for an estimate
SKIPPED = "SKIPPED"
NO_PROVIDER_MESSAGE = "No render provider is ready for this batch. Check the setup of each one."
_ERROR_BY_REFUSAL = {
    REFUSAL_NOT_READY: ProviderChoiceError.PROVIDER_NOT_READY,
    REFUSAL_DATA_CLASS: ProviderChoiceError.PROVIDER_NOT_ALLOWED,
}


@dataclass(frozen=True)
class ProviderOption:
    """One provider as the chooser shows it for one batch."""

    provider: Provider
    setup: SetupState
    estimate: Estimate | None
    spent_usd: float
    remaining_usd: float | None
    selectability: Selectability


@dataclass(frozen=True)
class ProviderChoices:
    """Every registered provider for one batch, plus the current choice."""

    data_class: str
    selected_provider_id: str | None
    options: list[ProviderOption]

    @property
    def any_selectable(self) -> bool:
        """True when at least one provider can be picked."""
        return any(o.selectability.selectable for o in self.options)

    @property
    def message(self) -> str | None:
        """A plain explanation when nothing can be picked."""
        return None if self.any_selectable else NO_PROVIDER_MESSAGE


class ProviderChooser:
    """Evaluates providers for a batch and enforces the choice rules."""

    def __init__(self, ctx: BatchContext) -> None:
        self._ctx = ctx

    def choices(self, uow: UnitOfWork, batch: BatchRecord) -> ProviderChoices:
        """All providers with setup state, estimate, credit and selectability."""
        registry = self._ctx.providers
        providers = () if registry is None else registry.providers
        rows = self._live_rows(uow, batch)
        options = [self._option(uow, batch, p, rows) for p in providers]
        return ProviderChoices(batch.data_class, batch.provider_id, options)

    def require_selectable(self, uow: UnitOfWork, batch: BatchRecord, provider_id: str) -> Provider:
        """The provider, or ProviderChoiceError when it cannot be chosen for this batch."""
        registry = self._ctx.providers
        provider = None if registry is None else registry.get(provider_id)
        if provider is None:
            raise ProviderChoiceError(ProviderChoiceError.UNKNOWN_PROVIDER)
        option = self._option(uow, batch, provider, self._live_rows(uow, batch))
        result = option.selectability
        if not result.selectable:
            code = _ERROR_BY_REFUSAL.get(
                result.code or "", ProviderChoiceError.PROVIDER_OVER_CREDIT
            )
            raise ProviderChoiceError(code)
        return provider

    def store_choice(self, uow: UnitOfWork, batch: BatchRecord, provider_id: str) -> BatchRecord:
        """Save ``provider_id`` on the batch (already checked) and commit; no-op if unchanged."""
        if batch.provider_id == provider_id:
            return batch
        batch = replace(batch, provider_id=provider_id)
        uow.batches.save(batch)
        audit(self._ctx, uow, "PROVIDER_CHOSEN", batch_id=str(batch.id), provider_id=provider_id)
        uow.commit()
        return batch

    def require_runnable(self, uow: UnitOfWork, batch: BatchRecord) -> None:
        """Start-time re-check of a stored provider: still ready, still allowed (not credit)."""
        registry = self._ctx.providers
        if batch.provider_id is None or registry is None:
            return
        try:
            provider = registry.for_batch(batch.provider_id)
        except UnknownProviderError:
            raise ProviderChoiceError(ProviderChoiceError.UNKNOWN_PROVIDER) from None
        result = check_selectable(
            provider,
            setup=self._setup(provider),
            data_class=DataClass(batch.data_class),
            estimate=None,
            spent=0.0,
        )
        if not result.selectable:
            raise ProviderChoiceError(_ERROR_BY_REFUSAL[result.code or REFUSAL_NOT_READY])

    # ---- helpers -----------------------------------------------------------------------

    def _setup(self, provider: Provider) -> SetupState:
        beats = self._ctx.queue_heartbeats
        alive = beats is not None and beats.is_alive(provider.queue)
        return setup_state(provider, env=self._ctx.provider_env, queue_alive=alive)

    @staticmethod
    def _live_rows(uow: UnitOfWork, batch: BatchRecord) -> int:
        counts = uow.batches.counts([batch.id])[batch.id]
        return sum(counts.values()) - counts.get(SKIPPED, 0)

    def _option(
        self, uow: UnitOfWork, batch: BatchRecord, provider: Provider, rows: int
    ) -> ProviderOption:
        registry = self._ctx.providers
        assert registry is not None  # noqa: S101 - callers return early without a registry
        owns_unrouted = registry.is_default(provider)
        runs = uow.batches.provider_runs(provider.id, owns_unrouted, MEASURED_WINDOW)
        estimate = estimate_for(provider, runs, rows)
        spent = uow.batches.provider_spent(provider.id, owns_unrouted)
        setup = self._setup(provider)
        result = check_selectable(
            provider,
            setup=setup,
            data_class=DataClass(batch.data_class),
            estimate=estimate,
            spent=spent,
        )
        return ProviderOption(
            provider, setup, estimate, spent, remaining_credit(provider, spent), result
        )


class ProviderFlow:
    """Listing providers and changing a batch's provider."""

    def __init__(self, ctx: BatchContext) -> None:
        self._ctx = ctx
        self._chooser = ProviderChooser(ctx)

    def list_for_batch(self, batch_id: UUID) -> ProviderChoices:
        """The chooser content for a batch."""
        with self._ctx.uow() as uow:
            return self._chooser.choices(uow, load_batch(uow, batch_id))

    def change_provider(self, batch_id: UUID, provider_id: str) -> BatchRecord:
        """Move a DRAFT or PAUSED batch to another provider; queued rows follow its queue."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            if batch.status not in (BatchState.DRAFT.value, BatchState.PAUSED.value):
                raise StateConflictError(StateConflictError.INVALID_STATE)
            self._chooser.require_selectable(uow, batch, provider_id)
            batch = replace(batch, provider_id=provider_id)
            uow.batches.save(batch)
            audit(ctx, uow, "PROVIDER_CHANGED", batch_id=str(batch_id), provider_id=provider_id)
            moved = (
                uow.batches.queued_row_ids(batch_id)
                if batch.status == BatchState.PAUSED.value
                else []
            )
            uow.commit()
        if moved:
            enqueue_rows(ctx, batch, moved)
        return batch
