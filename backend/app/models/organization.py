from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment
    from app.models.connector_account import ConnectorAccount


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    connector_accounts: Mapped[list["ConnectorAccount"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
