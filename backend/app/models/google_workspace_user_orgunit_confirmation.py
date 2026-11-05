from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class GoogleWorkspaceUserOrgUnitConfirmation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "google_workspace_user_orgunit_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "target_google_id",
            name="uq_google_user_orgunit_confirmation_target",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    connector_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("connector_configs.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    google_customer_id: Mapped[str] = mapped_column(String(255))
    target_google_id: Mapped[str] = mapped_column(String(255))
    target_primary_email: Mapped[str] = mapped_column(String(255))
    expected_source_path: Mapped[str] = mapped_column(String(1024))
    destination_org_unit_id: Mapped[str] = mapped_column(String(256))
    destination_path: Mapped[str] = mapped_column(String(1024))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(
        String(24), default="pending", server_default="pending"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
