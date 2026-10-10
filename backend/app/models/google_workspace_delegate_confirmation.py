from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class GoogleWorkspaceDelegateConfirmation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "google_workspace_delegate_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "operation",
            "owner_google_id",
            "delegate_google_id",
            name="uq_google_delegate_confirmation_operation",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_google_id: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_primary_email: Mapped[str] = mapped_column(String(255), nullable=False)
    delegate_google_id: Mapped[str] = mapped_column(String(255), nullable=False)
    delegate_primary_email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="pending", server_default="pending", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
