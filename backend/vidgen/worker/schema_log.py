"""Worker start-up report: one ERROR when the database is behind the code. Never migrates."""

from __future__ import annotations

import logging

from vidgen.services.schema_check import SchemaCheck, SchemaStatus

logger = logging.getLogger(__name__)


def report_schema_at_start(check: SchemaCheck) -> SchemaStatus:
    """Log the schema problem once and return the status; the worker starts either way."""
    status = check.status()
    if status.blocks:
        logger.error(status.message, extra={"schema_state": status.state.value})
    return status
