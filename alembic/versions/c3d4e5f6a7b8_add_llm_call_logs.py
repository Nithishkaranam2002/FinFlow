"""Add llm_call_logs table for LLM cost tracking."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("model_used", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_call_logs_tenant_id", "llm_call_logs", ["tenant_id"])
    op.create_index(
        "ix_llm_call_logs_tenant_id_created_at",
        "llm_call_logs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_llm_call_logs_tenant_id_agent_name",
        "llm_call_logs",
        ["tenant_id", "agent_name"],
    )
    op.create_index(
        "ix_llm_call_logs_tenant_id_model_used",
        "llm_call_logs",
        ["tenant_id", "model_used"],
    )
    op.create_index("ix_llm_call_logs_invoice_id", "llm_call_logs", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_call_logs_invoice_id", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_tenant_id_model_used", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_tenant_id_agent_name", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_tenant_id_created_at", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_tenant_id", table_name="llm_call_logs")
    op.drop_table("llm_call_logs")
