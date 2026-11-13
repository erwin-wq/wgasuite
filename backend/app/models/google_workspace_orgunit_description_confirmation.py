from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class GoogleWorkspaceOrgUnitDescriptionConfirmation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "google_workspace_orgunit_description_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "target_org_unit_id",
            name="uq_google_orgunit_description_target",
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
    target_org_unit_id: Mapped[str] = mapped_column(String(256))
    target_name: Mapped[str] = mapped_column(String(256))
    target_path: Mapped[str] = mapped_column(String(1024))
    parent_org_unit_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    parent_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    original_description: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    requested_description: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
