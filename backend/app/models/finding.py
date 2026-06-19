from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class Finding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("dread_damage BETWEEN 0 AND 10", name="ck_findings_dread_damage_range"),
        CheckConstraint(
            "dread_reproducibility BETWEEN 0 AND 10",
            name="ck_findings_dread_reproducibility_range",
        ),
        CheckConstraint(
            "dread_exploitability BETWEEN 0 AND 10",
            name="ck_findings_dread_exploitability_range",
        ),
        CheckConstraint(
            "dread_affected_users BETWEEN 0 AND 10",
            name="ck_findings_dread_affected_users_range",
        ),
        CheckConstraint(
            "dread_discoverability BETWEEN 0 AND 10",
            name="ck_findings_dread_discoverability_range",
        ),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_asset: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open", server_default="open")
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)

    dread_damage: Mapped[int] = mapped_column(Integer, nullable=False)
    dread_reproducibility: Mapped[int] = mapped_column(Integer, nullable=False)
    dread_exploitability: Mapped[int] = mapped_column(Integer, nullable=False)
    dread_affected_users: Mapped[int] = mapped_column(Integer, nullable=False)
    dread_discoverability: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        server_default="0",
        nullable=False,
    )

    assessment: Mapped["Assessment"] = relationship(back_populates="findings")
