"""Create initial DREAD assessment schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_name"), "organizations", ["name"], unique=True)

    op.create_table(
        "assessments",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column("scope_summary", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_assessments_organization_id"), "assessments", ["organization_id"], unique=False
    )

    op.create_table(
        "connector_accounts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="planned", nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_accounts_organization_id"),
        "connector_accounts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_accounts_provider"),
        "connector_accounts",
        ["provider"],
        unique=False,
    )

    op.create_table(
        "findings",
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("affected_asset", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="open", nullable=False),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("dread_damage", sa.Integer(), nullable=False),
        sa.Column("dread_reproducibility", sa.Integer(), nullable=False),
        sa.Column("dread_exploitability", sa.Integer(), nullable=False),
        sa.Column("dread_affected_users", sa.Integer(), nullable=False),
        sa.Column("dread_discoverability", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dread_affected_users BETWEEN 0 AND 10", name="ck_findings_dread_affected_users_range"
        ),
        sa.CheckConstraint("dread_damage BETWEEN 0 AND 10", name="ck_findings_dread_damage_range"),
        sa.CheckConstraint(
            "dread_discoverability BETWEEN 0 AND 10", name="ck_findings_dread_discoverability_range"
        ),
        sa.CheckConstraint(
            "dread_exploitability BETWEEN 0 AND 10", name="ck_findings_dread_exploitability_range"
        ),
        sa.CheckConstraint(
            "dread_reproducibility BETWEEN 0 AND 10", name="ck_findings_dread_reproducibility_range"
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_findings_assessment_id"), "findings", ["assessment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_findings_assessment_id"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_connector_accounts_provider"), table_name="connector_accounts")
    op.drop_index(op.f("ix_connector_accounts_organization_id"), table_name="connector_accounts")
    op.drop_table("connector_accounts")
    op.drop_index(op.f("ix_assessments_organization_id"), table_name="assessments")
    op.drop_table("assessments")
    op.drop_index(op.f("ix_organizations_name"), table_name="organizations")
    op.drop_table("organizations")
