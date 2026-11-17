"""JSON views and bodies of the render-provider chooser."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from vidgen.domain.providers import NOT_MEASURED_LABEL
from vidgen.services.provider_choice import ProviderChoices, ProviderOption

MAX_PROVIDER_ID_CHARS = 64


class ProviderBody(BaseModel):
    """Body naming a render provider."""

    provider_id: str = Field(min_length=1, max_length=MAX_PROVIDER_ID_CHARS)


class ApproveBody(BaseModel):
    """Optional body of the preview approval: the provider the Admin picked."""

    provider_id: str | None = Field(default=None, max_length=MAX_PROVIDER_ID_CHARS)


def _option_json(option: ProviderOption) -> dict[str, Any]:
    provider, estimate, result = option.provider, option.estimate, option.selectability
    refusal = None if result.selectable else {"code": result.code, "reason": result.reason}
    return {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind.value,
        "data_rule": provider.data_rule.value,
        "setup": {
            "state": "ready" if option.setup.ready else "needs_setup",
            "reason": option.setup.reason,
        },
        "estimate": None
        if estimate is None
        else {
            "seconds_per_video": estimate.seconds_per_video,
            "batch_seconds": estimate.batch_seconds,
            "batch_cost_usd": estimate.batch_cost_usd,
        },
        "estimate_label": NOT_MEASURED_LABEL if estimate is None else None,
        "spend_cap_usd": provider.spend_cap_usd,
        "spent_usd": option.spent_usd,
        "remaining_usd": option.remaining_usd,
        "selectable": result.selectable,
        "refusal": refusal,
    }


def choices_json(choices: ProviderChoices) -> dict[str, Any]:
    """The chooser list for one batch."""
    return {
        "data_class": choices.data_class,
        "selected_provider_id": choices.selected_provider_id,
        "any_selectable": choices.any_selectable,
        "message": choices.message,
        "providers": [_option_json(o) for o in choices.options],
    }
