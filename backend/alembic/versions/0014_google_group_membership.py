"""Add one-time Google group membership confirmations.

Revision ID: 0014_google_group_membership
Revises: 0013_gmail_delegation
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_google_group_membership"
down_revision: str | None = "0013_gmail_delegation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_workspace_group_membership_confirmations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("group_google_id", sa.String(length=255), nullable=False),
        sa.Column("group_primary_email", sa.String(length=255), nullable=False),
        sa.Column("member_google_id", sa.String(length=255), nullable=False),
        sa.Column("member_primary_email", sa.String(length=255), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "operation",
            "group_google_id",
            "member_google_id",
            name="uq_google_group_membership_confirmation_operation",
        ),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index(
        op.f("ix_google_workspace_group_membership_confirmations_actor_user_id"),
        "google_workspace_group_membership_confirmations",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_google_workspace_group_membership_confirmations_organization_id"),
        "google_workspace_group_membership_confirmations",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_google_workspace_group_membership_confirmations_organization_id"),
        table_name="google_workspace_group_membership_confirmations",
    )
    op.drop_index(
        op.f("ix_google_workspace_group_membership_confirmations_actor_user_id"),
        table_name="google_workspace_group_membership_confirmations",
    )
    op.drop_table("google_workspace_group_membership_confirmations")
