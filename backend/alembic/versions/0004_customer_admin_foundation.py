"""Add customer admin foundation.

Revision ID: 0004_customer_admin_foundation
Revises: 0003_auth_foundation
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_customer_admin_foundation"
down_revision: str | None = "0003_auth_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_CUSTOMER_ID = "00000000-0000-4000-8000-000000000101"


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index(op.f("ix_customers_slug"), "customers", ["slug"], unique=True)

    customers_table = sa.table(
        "customers",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("contact_name", sa.String),
        sa.column("contact_email", sa.String),
        sa.column("status", sa.String),
        sa.column("notes", sa.Text),
    )
    op.bulk_insert(
        customers_table,
        [
            {
                "id": DEMO_CUSTOMER_ID,
                "name": "Demo Customer",
                "slug": "demo-customer",
                "contact_name": None,
                "contact_email": None,
                "status": "active",
                "notes": "Development/demo customer for local testing.",
            }
        ],
    )

    op.add_column(
        "organizations",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_organizations_customer_id"),
        "organizations",
        ["customer_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_organizations_customer_id_customers",
        "organizations",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_organizations_customer_id_customers",
        "organizations",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_organizations_customer_id"), table_name="organizations")
    op.drop_column("organizations", "customer_id")
    op.drop_index(op.f("ix_customers_slug"), table_name="customers")
    op.drop_table("customers")
