"""Several name slots per template: the templates.extra_slots column (DD-40).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31

Rules (D-14): additive only. The column is nullable with no default, so existing rows read
as no extra slots. Downgrade drops exactly that column and keeps every other column and row.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable extra_slots column to templates."""
    op.add_column(
        "templates",
        sa.Column("extra_slots", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Drop the extra_slots column; nothing else changes."""
    op.drop_column("templates", "extra_slots")
