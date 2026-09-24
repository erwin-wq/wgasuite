"""Add non-secret Google Workspace credential references.

Revision ID: 0010_google_credentials
Revises: 0009_public_auth_cleanup
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_google_credentials"
down_revision: str | None = "0009_public_auth_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "connector_configs",
        sa.Column(
            "credential_provider",
            sa.String(length=80),
            server_default="file",
            nullable=False,
        ),
    )
    op.add_column(
        "connector_configs",
        sa.Column("credential_ref", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("connector_configs", "credential_ref")
    op.drop_column("connector_configs", "credential_provider")
