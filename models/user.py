import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.enums import pg_enum
from models.mixins import TenantScopedMixin

if TYPE_CHECKING:
    from models.tenant import Tenant


class UserRole(str, enum.Enum):
    AP_CLERK = "ap_clerk"
    APPROVER = "approver"
    CONTROLLER = "controller"
    AUDITOR = "auditor"


class User(TenantScopedMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_tenant_id_email", "tenant_id", "email", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
