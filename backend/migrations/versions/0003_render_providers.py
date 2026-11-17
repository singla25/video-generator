"""Render providers: batches.provider_id, batches.data_class, batch_rows.cost_usd.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

Rules (D-14): additive only. ``provider_id`` is nullable (null = the default provider),
``data_class`` defaults to ``real`` so every old batch stays real data (C5), ``cost_usd`` is
nullable (no measured cost). Downgrade drops exactly these columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the provider, data class and cost columns."""
    op.add_column("batches", sa.Column("provider_id", sa.String(64), nullable=True))
    op.add_column(
        "batches",
        sa.Column("data_class", sa.String(16), nullable=False, server_default="real"),
    )
    op.add_column("batch_rows", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))


def downgrade() -> None:
    """Drop the three columns; nothing else changes."""
    op.drop_column("batch_rows", "cost_usd")
    op.drop_column("batches", "data_class")
    op.drop_column("batches", "provider_id")
