"""Add one-time Gmail delegate confirmations.

Revision ID: 0013_gmail_delegation
Revises: 0012_google_credential_metadata
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_gmail_delegation"
down_revision: str | None = "0012_google_credential_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_workspace_delegate_confirmations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("owner_google_id", sa.String(length=255), nullable=False),
        sa.Column("owner_primary_email", sa.String(length=255), nullable=False),
        sa.Column("delegate_google_id", sa.String(length=255), nullable=False),
        sa.Column("delegate_primary_email", sa.String(length=255), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "operation",
            "owner_google_id",
            "delegate_google_id",
            name="uq_google_delegate_confirmation_operation",
        ),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index(
        op.f("ix_google_workspace_delegate_confirmations_actor_user_id"),
        "google_workspace_delegate_confirmations",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_google_workspace_delegate_confirmations_organization_id"),
        "google_workspace_delegate_confirmations",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_google_workspace_delegate_confirmations_organization_id"),
        table_name="google_workspace_delegate_confirmations",
    )
    op.drop_index(
        op.f("ix_google_workspace_delegate_confirmations_actor_user_id"),
        table_name="google_workspace_delegate_confirmations",
    )
    op.drop_table("google_workspace_delegate_confirmations")
