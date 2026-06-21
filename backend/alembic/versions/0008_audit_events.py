"""Add audit events.

Revision ID: 0008_audit_events
Revises: 0007_customer_memberships
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_audit_events"
down_revision: str | None = "0007_customer_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("actor_role", sa.String(length=40), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("object_type", sa.String(length=120), nullable=False),
        sa.Column("object_id", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=40), server_default="success", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], unique=False)
    op.create_index(
        op.f("ix_audit_events_actor_user_id"),
        "audit_events",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_created_at"),
        "audit_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_customer_id"),
        "audit_events",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_object_type"),
        "audit_events",
        ["object_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_object_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_customer_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_user_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_table("audit_events")
