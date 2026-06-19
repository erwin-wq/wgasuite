"""Add assets and DREAD score entity.

Revision ID: 0002_backend_core_crud
Revises: 0001_initial_schema
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_backend_core_crud"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=80), server_default="system", nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_assets_organization_name"),
    )
    op.create_index(op.f("ix_assets_organization_id"), "assets", ["organization_id"], unique=False)

    op.add_column("findings", sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_findings_asset_id"), "findings", ["asset_id"], unique=False)
    op.create_foreign_key(
        "fk_findings_asset_id_assets",
        "findings",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "ck_findings_dread_affected_users_range",
        "findings",
        type_="check",
    )
    op.drop_constraint("ck_findings_dread_damage_range", "findings", type_="check")
    op.drop_constraint(
        "ck_findings_dread_discoverability_range",
        "findings",
        type_="check",
    )
    op.drop_constraint(
        "ck_findings_dread_exploitability_range",
        "findings",
        type_="check",
    )
    op.drop_constraint(
        "ck_findings_dread_reproducibility_range",
        "findings",
        type_="check",
    )
    op.drop_column("findings", "risk_score")
    op.drop_column("findings", "dread_discoverability")
    op.drop_column("findings", "dread_affected_users")
    op.drop_column("findings", "dread_exploitability")
    op.drop_column("findings", "dread_reproducibility")
    op.drop_column("findings", "dread_damage")
    op.drop_column("findings", "affected_asset")

    op.create_table(
        "dread_scores",
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=False),
        sa.Column("reproducibility", sa.Integer(), nullable=False),
        sa.Column("exploitability", sa.Integer(), nullable=False),
        sa.Column("affected_users", sa.Integer(), nullable=False),
        sa.Column("discoverability", sa.Integer(), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
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
            "affected_users BETWEEN 0 AND 10",
            name="ck_dread_scores_affected_users_range",
        ),
        sa.CheckConstraint("damage BETWEEN 0 AND 10", name="ck_dread_scores_damage_range"),
        sa.CheckConstraint(
            "discoverability BETWEEN 0 AND 10",
            name="ck_dread_scores_discoverability_range",
        ),
        sa.CheckConstraint(
            "exploitability BETWEEN 0 AND 10",
            name="ck_dread_scores_exploitability_range",
        ),
        sa.CheckConstraint(
            "reproducibility BETWEEN 0 AND 10",
            name="ck_dread_scores_reproducibility_range",
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dread_scores_finding_id"), "dread_scores", ["finding_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_dread_scores_finding_id"), table_name="dread_scores")
    op.drop_table("dread_scores")

    op.add_column(
        "findings",
        sa.Column("affected_asset", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("dread_damage", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "findings",
        sa.Column("dread_reproducibility", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "findings",
        sa.Column("dread_exploitability", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "findings",
        sa.Column("dread_affected_users", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "findings",
        sa.Column("dread_discoverability", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "findings",
        sa.Column("risk_score", sa.Float(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_findings_dread_damage_range",
        "findings",
        "dread_damage BETWEEN 0 AND 10",
    )
    op.create_check_constraint(
        "ck_findings_dread_reproducibility_range",
        "findings",
        "dread_reproducibility BETWEEN 0 AND 10",
    )
    op.create_check_constraint(
        "ck_findings_dread_exploitability_range",
        "findings",
        "dread_exploitability BETWEEN 0 AND 10",
    )
    op.create_check_constraint(
        "ck_findings_dread_affected_users_range",
        "findings",
        "dread_affected_users BETWEEN 0 AND 10",
    )
    op.create_check_constraint(
        "ck_findings_dread_discoverability_range",
        "findings",
        "dread_discoverability BETWEEN 0 AND 10",
    )

    op.drop_constraint("fk_findings_asset_id_assets", "findings", type_="foreignkey")
    op.drop_index(op.f("ix_findings_asset_id"), table_name="findings")
    op.drop_column("findings", "asset_id")
    op.drop_index(op.f("ix_assets_organization_id"), table_name="assets")
    op.drop_table("assets")
