"""Add guarded Google organizational-unit description confirmations.

Revision ID: 0018_google_orgunit_description
Revises: 0017_google_orgunit_creation
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_google_orgunit_description"
down_revision: str | None = "0017_google_orgunit_creation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_workspace_orgunit_description_confirmations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("google_customer_id", sa.String(255), nullable=False),
        sa.Column("target_org_unit_id", sa.String(256), nullable=False),
        sa.Column("target_name", sa.String(256), nullable=False),
        sa.Column("target_path", sa.String(1024), nullable=False),
        sa.Column("parent_org_unit_id", sa.String(256), nullable=True),
        sa.Column("parent_path", sa.String(1024), nullable=True),
        sa.Column("original_description", sa.String(4096), nullable=True),
        sa.Column("requested_description", sa.String(4096), nullable=True),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connector_config_id"], ["connector_configs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
        sa.UniqueConstraint(
            "organization_id",
            "target_org_unit_id",
            name="uq_google_orgunit_description_target",
        ),
    )
    for column in ("organization_id", "customer_id", "connector_config_id", "actor_user_id"):
        op.create_index(
            op.f(f"ix_google_workspace_orgunit_description_confirmations_{column}"),
            "google_workspace_orgunit_description_confirmations",
            [column],
        )


def downgrade() -> None:
    op.drop_table("google_workspace_orgunit_description_confirmations")
