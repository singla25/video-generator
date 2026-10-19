"""Initial schema: campaigns, templates, consent, batches, rows, login state, audit log.

Revision ID: 0001
Revises:
Create Date: 2026-10-19

Rules (D-14): upgrade only creates tables and indexes; downgrade drops exactly those tables in
reverse order. Personal data (name, spoken name, voter ID) exists only as encrypted bytes plus
a keyed blind index; there are no plaintext personal-data columns.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _campaign_id() -> sa.Column[sa.Uuid]:
    """The required campaign reference carried by every table except campaigns (D6)."""
    return sa.Column("campaign_id", sa.Uuid(), nullable=False)


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def _campaign_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["campaign_id"], ["campaigns.id"], name=f"fk_{table}_campaign_id_campaigns"
    )


def upgrade() -> None:
    """Create the six tables and their indexes."""
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_campaigns"),
    )

    op.create_table(
        "templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        _campaign_id(),
        sa.Column("video_key", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=200), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("slot_start_s", sa.Float(), nullable=True),
        sa.Column("slot_end_s", sa.Float(), nullable=True),
        sa.Column("slot_source", sa.String(length=16), nullable=True),
        sa.Column("slot_confidence", sa.Float(), nullable=True),
        sa.Column("slot_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("slot_error", sa.String(length=64), nullable=True),
        sa.Column("analysed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("face_region", postgresql.JSONB(), nullable=True),
        sa.Column(
            "consent_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        _created_at(),
        _campaign_fk("templates"),
        sa.PrimaryKeyConstraint("id", name="pk_templates"),
    )
    op.create_index("ix_templates_campaign_id", "templates", ["campaign_id"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        _campaign_id(),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("file_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        _created_at(),
        _campaign_fk("consent_records"),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
            name="fk_consent_records_template_id_templates",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_consent_records"),
    )
    op.create_index("ix_consent_records_template_id", "consent_records", ["template_id"])

    op.create_table(
        "batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        _campaign_id(),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
        sa.Column("sheet_key", sa.String(length=500), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=True),
        sa.Column("folder_name", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        _created_at(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _campaign_fk("batches"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["templates.id"], name="fk_batches_template_id_templates"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batches"),
        sa.UniqueConstraint("idempotency_key", name="uq_batches_idempotency_key"),
    )
    op.create_index("ix_batches_campaign_id_status", "batches", ["campaign_id", "status"])
    op.create_index("ix_batches_template_id", "batches", ["template_id"])
    op.create_index("ix_batches_finished_at", "batches", ["finished_at"])

    op.create_table(
        "batch_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        _campaign_id(),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("name_enc", sa.LargeBinary(), nullable=False),
        sa.Column("spoken_name_enc", sa.LargeBinary(), nullable=True),
        sa.Column("voter_id_enc", sa.LargeBinary(), nullable=False),
        sa.Column("voter_id_index", sa.String(length=64), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_key", sa.String(length=500), nullable=True),
        sa.Column("render_seconds", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _campaign_fk("batch_rows"),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["batches.id"], name="fk_batch_rows_batch_id_batches", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batch_rows"),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_batch_rows_batch_id_row_number"),
    )
    op.create_index("ix_batch_rows_batch_id_status", "batch_rows", ["batch_id", "status"])
    op.create_index(
        "ix_batch_rows_batch_id_voter_id_index", "batch_rows", ["batch_id", "voter_id_index"]
    )

    op.create_index(
        "uq_batch_rows_batch_id_voter_id_index_live",
        "batch_rows",
        ["batch_id", "voter_id_index"],
        unique=True,
        postgresql_where=sa.text("status <> 'SKIPPED'"),
    )

    op.create_table(
        "login_attempts",
        _campaign_id(),
        sa.Column("client_key", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_allowed_at", sa.DateTime(timezone=True), nullable=True),
        _campaign_fk("login_attempts"),
        sa.PrimaryKeyConstraint("campaign_id", "client_key", name="pk_login_attempts"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        _campaign_id(),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        _campaign_fk("audit_log"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_campaign_id_at", "audit_log", ["campaign_id", "at"])


def downgrade() -> None:
    """Drop exactly the tables created above, in reverse order (indexes go with them)."""
    op.drop_table("audit_log")
    op.drop_table("login_attempts")
    op.drop_table("batch_rows")
    op.drop_table("batches")
    op.drop_table("consent_records")
    op.drop_table("templates")
    op.drop_table("campaigns")
