"""Disable the unchanged legacy fixed development credential.

Revision ID: 0009_public_auth_cleanup
Revises: 0008_audit_events
Create Date: 2026-09-18
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_public_auth_cleanup"
down_revision: str | None = "0008_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_DEVELOPMENT_ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
LEGACY_DEVELOPMENT_ADMIN_EMAIL = "admin@example.local"
LEGACY_DEVELOPMENT_ADMIN_HASH = (
    "pbkdf2_sha256$260000$dev-demo-admin-salt$"
    "88197364a117d2eee1e2e6bce0fa727ee1fd69f3477c343fb956dd0a5d7f2084"
)
DISABLED_PASSWORD_HASH = "disabled-legacy-development-credential"


def upgrade() -> None:
    users = sa.table(
        "users",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("email", sa.String),
        sa.column("full_name", sa.String),
        sa.column("hashed_password", sa.String),
        sa.column("role", sa.String),
        sa.column("is_active", sa.Boolean()),
    )
    connection = op.get_bind()
    connection.execute(
        users.update()
        .where(
            sa.and_(
                sa.or_(
                    users.c.id == LEGACY_DEVELOPMENT_ADMIN_ID,
                    users.c.email == LEGACY_DEVELOPMENT_ADMIN_EMAIL,
                ),
                users.c.hashed_password == LEGACY_DEVELOPMENT_ADMIN_HASH,
            )
        )
        .values(
            hashed_password=DISABLED_PASSWORD_HASH,
            is_active=False,
        )
    )


def downgrade() -> None:
    # The removed fixed credential must never be restored by a downgrade.
    pass
