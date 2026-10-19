"""Conversion between batch records and ORM rows (the JSON document in ``column_mapping``).

The document holds column names, the sheet name and the preview state: ids and settings only,
never personal data.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from vidgen.domain.status import ApprovalFingerprint
from vidgen.infrastructure.db.models import Batch
from vidgen.ports.batches import BatchRecord, MappingRecord, PreviewRecord


def _fingerprint_json(fp: ApprovalFingerprint | None) -> dict[str, Any] | None:
    if fp is None:
        return None
    return {
        "slot_start_s": fp.slot_start_s,
        "slot_end_s": fp.slot_end_s,
        "template_id": fp.template_id,
        "mapping": list(fp.mapping),
    }


def _fingerprint_from(data: dict[str, Any] | None) -> ApprovalFingerprint | None:
    if data is None:
        return None
    return ApprovalFingerprint(
        data["slot_start_s"], data["slot_end_s"], data["template_id"], tuple(data["mapping"])
    )


def to_document(batch: BatchRecord) -> dict[str, Any]:
    """The JSON document stored in ``batches.column_mapping``."""
    preview = batch.preview
    mapping = batch.mapping
    return {
        "sheet_name": batch.sheet_name,
        "mapping": None
        if mapping is None
        else {
            "name_column": mapping.name_column,
            "id_column": mapping.id_column,
            "spoken_name_column": mapping.spoken_name_column,
            "name_index": mapping.name_index,
            "id_index": mapping.id_index,
            "spoken_name_index": mapping.spoken_name_index,
        },
        "preview": {
            "status": preview.status,
            "key": preview.key,
            "row_id": None if preview.row_id is None else str(preview.row_id),
            "failure_code": preview.failure_code,
            "requested_for": _fingerprint_json(preview.requested_for),
            "rendered_for": _fingerprint_json(preview.rendered_for),
            "approved_for": _fingerprint_json(preview.approved_for),
        },
    }


def to_record(row: Batch) -> BatchRecord:
    """The batch record described by an ORM row and its JSON document."""
    document: dict[str, Any] = row.column_mapping or {}
    mapping = document.get("mapping")
    preview = document.get("preview") or {}
    return BatchRecord(
        id=row.id,
        template_id=row.template_id,
        status=row.status,
        created_at=row.created_at,
        sheet_key=row.sheet_key,
        sheet_name=document.get("sheet_name"),
        folder_name=row.folder_name,
        idempotency_key=row.idempotency_key,
        started_at=row.started_at,
        finished_at=row.finished_at,
        mapping=None if mapping is None else MappingRecord(**mapping),
        preview=PreviewRecord(
            status=preview.get("status", "NONE"),
            key=preview.get("key"),
            row_id=UUID(preview["row_id"]) if preview.get("row_id") else None,
            failure_code=preview.get("failure_code"),
            requested_for=_fingerprint_from(preview.get("requested_for")),
            rendered_for=_fingerprint_from(preview.get("rendered_for")),
            approved_for=_fingerprint_from(preview.get("approved_for")),
        ),
    )


def apply_to_row(row: Batch, batch: BatchRecord) -> None:
    """Copy a batch record onto its ORM row."""
    row.template_id = batch.template_id
    row.status = batch.status
    row.sheet_key = batch.sheet_key
    row.folder_name = batch.folder_name
    row.idempotency_key = batch.idempotency_key
    row.created_at = batch.created_at
    row.started_at = batch.started_at
    row.finished_at = batch.finished_at
    row.column_mapping = to_document(batch)
