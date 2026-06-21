from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.customer_membership import CustomerMembership
    from app.models.organization import Organization


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", server_default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    organizations: Mapped[list["Organization"]] = relationship(back_populates="customer")
    memberships: Mapped[list["CustomerMembership"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )
