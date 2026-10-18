"""Read-only audit log endpoint (C4). There are deliberately no write routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from vidgen.api.deps import container, require_csrf
from vidgen.api.schemas import audit_json

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_csrf)])


@router.get("")
def list_audit(request: Request, action: str | None = None) -> dict[str, Any]:
    """Audit entries oldest first, optionally only one action."""
    entries = container(request).audit.entries(action)
    return {"entries": [audit_json(e) for e in entries]}
