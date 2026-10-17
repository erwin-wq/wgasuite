from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class GoogleWorkspaceUserStatusConfirmation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "google_workspace_user_status_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "operation",
            "target_google_id",
            name="uq_google_user_status_confirmation_operation",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    connector_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("connector_configs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    google_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    target_google_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_primary_email: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requested_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_suspension_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="pending", server_default="pending", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
