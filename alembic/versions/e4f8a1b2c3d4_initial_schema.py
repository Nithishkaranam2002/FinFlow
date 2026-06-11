"""initial_schema

Revision ID: e4f8a1b2c3d4
Revises:
Create Date: 2026-06-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4f8a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

invoice_status_enum = postgresql.ENUM(
    "received",
    "extracting",
    "review_required",
    "matched",
    "approved",
    "rejected",
    "paid",
    name="invoice_status",
    create_type=False,
)

payment_status_enum = postgresql.ENUM(
    "scheduled",
    "sent",
    "cleared",
    "failed",
    name="payment_status",
    create_type=False,
)

match_type_enum = postgresql.ENUM(
    "exact",
    "fuzzy",
    "llm_judgment",
    "manual",
    "unmatched",
    name="match_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    invoice_status_enum.create(bind, checkfirst=True)
    payment_status_enum.create(bind, checkfirst=True)
    match_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("bank_account", sa.String(length=64), nullable=True),
        sa.Column("bank_account_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payment_terms_days",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "total_invoices",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_paid",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "risk_score",
            sa.Float(),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendors_tenant_id", "vendors", ["tenant_id"], unique=False)
    op.create_index(
        "ix_vendors_tenant_id_is_active",
        "vendors",
        ["tenant_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "line_items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            invoice_status_enum,
            server_default=sa.text("'received'"),
            nullable=False,
        ),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_tenant_id", "invoices", ["tenant_id"], unique=False)
    op.create_index(
        "ix_invoices_tenant_id_status",
        "invoices",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index("ix_invoices_vendor_id", "invoices", ["vendor_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "status",
            payment_status_enum,
            server_default=sa.text("'scheduled'"),
            nullable=False,
        ),
        sa.Column("payment_reference", sa.String(length=128), nullable=True),
        sa.Column("bank_transaction_id", sa.String(length=128), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"], unique=False)
    op.create_index(
        "ix_payments_tenant_id_status",
        "payments",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"], unique=False)

    op.create_table(
        "reconciliation_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_line_id", sa.String(length=128), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "match_type",
            match_type_enum,
            server_default=sa.text("'unmatched'"),
            nullable=False,
        ),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("llm_reasoning", sa.Text(), nullable=True),
        sa.Column("matched_by", sa.String(length=128), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reconciliation_matches_tenant_id",
        "reconciliation_matches",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_matches_tenant_id_match_type",
        "reconciliation_matches",
        ["tenant_id", "match_type"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_matches_invoice_id",
        "reconciliation_matches",
        ["invoice_id"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_matches_payment_id",
        "reconciliation_matches",
        ["payment_id"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"], unique=False)
    op.create_index(
        "ix_audit_logs_tenant_id_entity",
        "audit_logs",
        ["tenant_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_id_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(
        "ix_reconciliation_matches_payment_id",
        table_name="reconciliation_matches",
    )
    op.drop_index(
        "ix_reconciliation_matches_invoice_id",
        table_name="reconciliation_matches",
    )
    op.drop_index(
        "ix_reconciliation_matches_tenant_id_match_type",
        table_name="reconciliation_matches",
    )
    op.drop_index(
        "ix_reconciliation_matches_tenant_id",
        table_name="reconciliation_matches",
    )
    op.drop_table("reconciliation_matches")

    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_tenant_id_status", table_name="payments")
    op.drop_index("ix_payments_tenant_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("ix_invoices_vendor_id", table_name="invoices")
    op.drop_index("ix_invoices_tenant_id_status", table_name="invoices")
    op.drop_index("ix_invoices_tenant_id", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_vendors_tenant_id_is_active", table_name="vendors")
    op.drop_index("ix_vendors_tenant_id", table_name="vendors")
    op.drop_table("vendors")

    bind = op.get_bind()
    match_type_enum.drop(bind, checkfirst=True)
    payment_status_enum.drop(bind, checkfirst=True)
    invoice_status_enum.drop(bind, checkfirst=True)
