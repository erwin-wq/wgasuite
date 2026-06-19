from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.finding import Finding


class DreadScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dread_scores"
    __table_args__ = (
        CheckConstraint("damage BETWEEN 0 AND 10", name="ck_dread_scores_damage_range"),
        CheckConstraint(
            "reproducibility BETWEEN 0 AND 10",
            name="ck_dread_scores_reproducibility_range",
        ),
        CheckConstraint(
            "exploitability BETWEEN 0 AND 10",
            name="ck_dread_scores_exploitability_range",
        ),
        CheckConstraint(
            "affected_users BETWEEN 0 AND 10",
            name="ck_dread_scores_affected_users_range",
        ),
        CheckConstraint(
            "discoverability BETWEEN 0 AND 10",
            name="ck_dread_scores_discoverability_range",
        ),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("findings.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    damage: Mapped[int] = mapped_column(Integer, nullable=False)
    reproducibility: Mapped[int] = mapped_column(Integer, nullable=False)
    exploitability: Mapped[int] = mapped_column(Integer, nullable=False)
    affected_users: Mapped[int] = mapped_column(Integer, nullable=False)
    discoverability: Mapped[int] = mapped_column(Integer, nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)

    finding: Mapped["Finding"] = relationship(back_populates="dread_score")
