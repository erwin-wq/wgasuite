"""Add one-time Google user status confirmations.

Revision ID: 0015_google_user_status
Revises: 0014_google_group_membership
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_google_user_status"
down_revision: str | None = "0014_google_group_membership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_workspace_user_status_confirmations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("google_customer_id", sa.String(length=255), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("target_google_id", sa.String(length=255), nullable=False),
        sa.Column("target_primary_email", sa.String(length=255), nullable=False),
        sa.Column("expected_suspended", sa.Boolean(), nullable=False),
        sa.Column("requested_suspended", sa.Boolean(), nullable=False),
        sa.Column("expected_suspension_reason", sa.String(length=255), nullable=True),
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
            ["connector_config_id"], ["connector_configs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "operation",
            "target_google_id",
            name="uq_google_user_status_confirmation_operation",
        ),
        sa.UniqueConstraint("token_digest"),
    )
    for column in (
        "actor_user_id",
        "connector_config_id",
        "customer_id",
        "organization_id",
    ):
        op.create_index(
            op.f(f"ix_google_workspace_user_status_confirmations_{column}"),
            "google_workspace_user_status_confirmations",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "organization_id",
        "customer_id",
        "connector_config_id",
        "actor_user_id",
    ):
        op.drop_index(
            op.f(f"ix_google_workspace_user_status_confirmations_{column}"),
            table_name="google_workspace_user_status_confirmations",
        )
    op.drop_table("google_workspace_user_status_confirmations")
