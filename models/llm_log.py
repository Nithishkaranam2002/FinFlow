import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"
    __table_args__ = (
        Index("ix_llm_call_logs_tenant_id", "tenant_id"),
        Index("ix_llm_call_logs_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_llm_call_logs_tenant_id_agent_name", "tenant_id", "agent_name"),
        Index("ix_llm_call_logs_tenant_id_model_used", "tenant_id", "model_used"),
        Index("ix_llm_call_logs_invoice_id", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cache_hit: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
