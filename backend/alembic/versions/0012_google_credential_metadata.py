"""Add safe Google service-account metadata.

Revision ID: 0012_google_credential_metadata
Revises: 0011_google_connection_test
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_google_credential_metadata"
down_revision: str | None = "0011_google_connection_test"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "connector_configs",
        sa.Column("service_account_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "connector_configs",
        sa.Column("service_account_client_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("connector_configs", "service_account_client_id")
    op.drop_column("connector_configs", "service_account_email")
