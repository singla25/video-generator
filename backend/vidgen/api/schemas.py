"""Request and response shapes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from vidgen.ports import AuditEntry, TemplateRecord

MAX_PASSWORD_CHARS = 1024


class LoginRequest(BaseModel):
    """Body of the login request."""

    password: str = Field(max_length=MAX_PASSWORD_CHARS)


class SlotRequest(BaseModel):
    """Body of the slot request; infinities and NaN are refused at the boundary."""

    start_s: float = Field(allow_inf_nan=False)
    end_s: float = Field(allow_inf_nan=False)


def template_json(template: TemplateRecord) -> dict[str, Any]:
    """Public view of a template."""
    slot = template.slot
    return {
        "id": str(template.id),
        "original_name": template.original_name,
        "duration_s": template.duration_s,
        "width": template.width,
        "height": template.height,
        "slot": None if slot is None else {"start_s": slot[0], "end_s": slot[1]},
        "slot_source": template.slot_source,
        "slot_confidence": template.slot_confidence,
        "slot_confirmed": template.slot_confirmed,
        "slot_error": template.slot_error,
        "needs_manual_slot": template.needs_manual_slot,
        "consent_confirmed": template.consent_confirmed,
        "usable": template.usable,
        "created_at": None if template.created_at is None else template.created_at.isoformat(),
    }


def audit_json(entry: AuditEntry) -> dict[str, Any]:
    """Public view of an audit entry."""
    return {
        "at": entry.at.isoformat(),
        "actor": entry.actor,
        "action": entry.action,
        "details": entry.details,
    }
