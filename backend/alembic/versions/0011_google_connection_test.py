"""Persist real Google Workspace connection-test state.

Revision ID: 0011_google_connection_test
Revises: 0010_google_credentials
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_google_connection_test"
down_revision: str | None = "0010_google_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "connector_configs",
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "connector_configs",
        sa.Column(
            "connection_config_revision",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    # GW-001 exposed no real probe and allowed callers to supply status. No legacy green or failed
    # state is valid evidence for GW-002, and placeholder test timestamps/errors are not retained.
    op.execute(
        sa.text(
            """
            UPDATE connector_configs
            SET status = CASE
                    WHEN status IN ('connected', 'connection_failed') THEN 'configured'
                    ELSE status
                END,
                last_tested_at = NULL,
                last_error = NULL
            WHERE connector_type = 'google_workspace'
            """
        )
    )
    op.add_column(
        "connector_configs",
        sa.Column(
            "connection_test_generation",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("connector_configs", "connection_test_generation")
    op.drop_column("connector_configs", "connection_config_revision")
    op.drop_column("connector_configs", "last_error_code")
