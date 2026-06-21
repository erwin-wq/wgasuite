"""Add Google Workspace connector configuration.

Revision ID: 0006_connector_config
Revises: 0005_mock_google_workspace_scan
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_connector_config"
down_revision: str | None = "0005_mock_google_workspace_scan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connector_configs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connector_type",
            sa.String(length=80),
            server_default="google_workspace",
            nullable=False,
        ),
        sa.Column(
            "auth_method",
            sa.String(length=80),
            server_default="service_account_domain_wide_delegation",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=40), server_default="not_configured", nullable=False),
        sa.Column(
            "display_name",
            sa.String(length=255),
            server_default="Google Workspace",
            nullable=False,
        ),
        sa.Column("primary_domain", sa.String(length=255), nullable=True),
        sa.Column("admin_subject_email", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "connector_type",
            name="uq_connector_configs_organization_type",
        ),
    )
    op.create_index(
        op.f("ix_connector_configs_organization_id"),
        "connector_configs",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_connector_configs_organization_id"), table_name="connector_configs")
    op.drop_table("connector_configs")
