"""Render-provider endpoints: the chooser list and the provider change (AC4-AC6)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from vidgen.api.deps import container, require_csrf
from vidgen.api.schemas_batches import batch_json
from vidgen.api.schemas_providers import ProviderBody, choices_json

router = APIRouter(prefix="/batches", tags=["providers"], dependencies=[Depends(require_csrf)])


@router.get("/{batch_id}/providers")
def list_providers(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Every registered provider for this batch: setup, estimate, credit and refusal."""
    return choices_json(container(request).batches.provider_choices(batch_id))


@router.put("/{batch_id}/provider")
def change_provider(batch_id: UUID, body: ProviderBody, request: Request) -> dict[str, Any]:
    """Move a draft or paused batch to another provider; queued rows follow."""
    return batch_json(container(request).batches.change_provider(batch_id, body.provider_id))
