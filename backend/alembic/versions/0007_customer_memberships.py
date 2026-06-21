"""Add customer memberships and platform roles.

Revision ID: 0007_customer_memberships
Revises: 0006_connector_config
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_customer_memberships"
down_revision: str | None = "0006_connector_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_ADMIN_ID = "00000000-0000-4000-8000-000000000001"
DEMO_CUSTOMER_ID = "00000000-0000-4000-8000-000000000101"
DEMO_MEMBERSHIP_ID = "00000000-0000-4000-8000-000000000201"


def upgrade() -> None:
    op.create_table(
        "customer_memberships",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=40), server_default="customer_viewer", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "customer_id",
            name="uq_customer_memberships_user_customer",
        ),
    )
    op.create_index(
        op.f("ix_customer_memberships_customer_id"),
        "customer_memberships",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_memberships_user_id"),
        "customer_memberships",
        ["user_id"],
        unique=False,
    )

    op.execute("UPDATE users SET role = 'platform_admin' WHERE role = 'admin'")
    op.execute("UPDATE users SET role = 'customer_user' WHERE role IN ('viewer', 'assessor')")
    op.execute(
        sa.text(
            """
            INSERT INTO customer_memberships (
                id,
                user_id,
                customer_id,
                role,
                is_active
            )
            SELECT
                CAST(:membership_id AS uuid),
                CAST(:user_id AS uuid),
                CAST(:customer_id AS uuid),
                'customer_admin',
                TRUE
            WHERE EXISTS (
                SELECT 1 FROM users WHERE id = CAST(:user_id AS uuid)
            )
            AND EXISTS (
                SELECT 1 FROM customers WHERE id = CAST(:customer_id AS uuid)
            )
            """
        ).bindparams(
            membership_id=DEMO_MEMBERSHIP_ID,
            user_id=DEMO_ADMIN_ID,
            customer_id=DEMO_CUSTOMER_ID,
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_customer_memberships_user_id"), table_name="customer_memberships")
    op.drop_index(op.f("ix_customer_memberships_customer_id"), table_name="customer_memberships")
    op.drop_table("customer_memberships")
