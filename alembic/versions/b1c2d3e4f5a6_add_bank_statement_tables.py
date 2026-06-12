"""Bank statement tables and reconciliation match extensions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

statement_status_enum = postgresql.ENUM(
    "processing",
    "completed",
    "failed",
    name="statement_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    statement_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "bank_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("source_format", sa.String(length=32), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            statement_status_enum,
            server_default=sa.text("'processing'"),
            nullable=False,
        ),
        sa.Column("line_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("report_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bank_statements_tenant_id", "bank_statements", ["tenant_id"])
    op.create_index(
        "ix_bank_statements_tenant_id_status",
        "bank_statements",
        ["tenant_id", "status"],
    )

    op.create_table(
        "bank_statement_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("reference", sa.String(length=256), nullable=True),
        sa.Column("bank_transaction_id", sa.String(length=128), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("is_matched", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("exception_reason", sa.Text(), nullable=True),
        sa.Column("llm_explanation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["statement_id"], ["bank_statements.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bank_statement_lines_tenant_id", "bank_statement_lines", ["tenant_id"])
    op.create_index(
        "ix_bank_statement_lines_statement_id",
        "bank_statement_lines",
        ["statement_id"],
    )
    op.create_index(
        "ix_bank_statement_lines_tenant_id_is_matched",
        "bank_statement_lines",
        ["tenant_id", "is_matched"],
    )

    op.add_column(
        "reconciliation_matches",
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "reconciliation_matches",
        sa.Column("bank_statement_line_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_reconciliation_matches_statement_id",
        "reconciliation_matches",
        "bank_statements",
        ["statement_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_reconciliation_matches_bank_statement_line_id",
        "reconciliation_matches",
        "bank_statement_lines",
        ["bank_statement_line_id"],
        ["id"],
    )
    op.create_index(
        "ix_reconciliation_matches_statement_id",
        "reconciliation_matches",
        ["statement_id"],
    )
    op.create_index(
        "ix_reconciliation_matches_bank_line_id",
        "reconciliation_matches",
        ["bank_line_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_matches_bank_line_id", table_name="reconciliation_matches")
    op.drop_index("ix_reconciliation_matches_statement_id", table_name="reconciliation_matches")
    op.drop_constraint(
        "fk_reconciliation_matches_bank_statement_line_id",
        "reconciliation_matches",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_reconciliation_matches_statement_id",
        "reconciliation_matches",
        type_="foreignkey",
    )
    op.drop_column("reconciliation_matches", "bank_statement_line_id")
    op.drop_column("reconciliation_matches", "statement_id")

    op.drop_index(
        "ix_bank_statement_lines_tenant_id_is_matched",
        table_name="bank_statement_lines",
    )
    op.drop_index("ix_bank_statement_lines_statement_id", table_name="bank_statement_lines")
    op.drop_index("ix_bank_statement_lines_tenant_id", table_name="bank_statement_lines")
    op.drop_table("bank_statement_lines")

    op.drop_index("ix_bank_statements_tenant_id_status", table_name="bank_statements")
    op.drop_index("ix_bank_statements_tenant_id", table_name="bank_statements")
    op.drop_table("bank_statements")

    statement_status_enum.drop(op.get_bind(), checkfirst=True)
