"""Add auth user foundation.

Revision ID: 0003_auth_foundation
Revises: 0002_backend_core_crud
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_auth_foundation"
down_revision: str | None = "0002_backend_core_crud"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_ADMIN_ID = "00000000-0000-4000-8000-000000000001"
DEMO_ADMIN_EMAIL = "admin@example.local"
DEMO_ADMIN_HASH = (
    "pbkdf2_sha256$260000$dev-demo-admin-salt$"
    "88197364a117d2eee1e2e6bce0fa727ee1fd69f3477c343fb956dd0a5d7f2084"
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=40), server_default="viewer", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    users_table = sa.table(
        "users",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("email", sa.String),
        sa.column("full_name", sa.String),
        sa.column("hashed_password", sa.String),
        sa.column("role", sa.String),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        users_table,
        [
            {
                "id": DEMO_ADMIN_ID,
                "email": DEMO_ADMIN_EMAIL,
                "full_name": "Development Admin",
                "hashed_password": DEMO_ADMIN_HASH,
                "role": "admin",
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
