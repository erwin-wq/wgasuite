from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import PLATFORM_CUSTOMER_USER
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.customer_membership import CustomerMembership


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(
        String(40),
        default=PLATFORM_CUSTOMER_USER,
        server_default=PLATFORM_CUSTOMER_USER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    customer_memberships: Mapped[list["CustomerMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
