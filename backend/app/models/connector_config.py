from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class ConnectorConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "connector_configs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connector_type",
            name="uq_connector_configs_organization_type",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    connector_type: Mapped[str] = mapped_column(
        String(80),
        default="google_workspace",
        server_default="google_workspace",
        nullable=False,
    )
    auth_method: Mapped[str] = mapped_column(
        String(80),
        default="service_account_domain_wide_delegation",
        server_default="service_account_domain_wide_delegation",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(40),
        default="not_configured",
        server_default="not_configured",
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        default="Google Workspace",
        server_default="Google Workspace",
        nullable=False,
    )
    primary_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_subject_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_provider: Mapped[str] = mapped_column(
        String(80),
        default="file",
        server_default="file",
        nullable=False,
    )
    credential_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="connector_configs")

    @property
    def credentials_configured(self) -> bool:
        return bool(self.credential_provider and self.credential_ref)
