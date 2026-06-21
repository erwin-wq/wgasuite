from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import CUSTOMER_VIEWER
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.user import User


class CustomerMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "customer_id", name="uq_customer_memberships_user_customer"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(40),
        default=CUSTOMER_VIEWER,
        server_default=CUSTOMER_VIEWER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    user: Mapped["User"] = relationship(back_populates="customer_memberships")
    customer: Mapped["Customer"] = relationship(back_populates="memberships")
