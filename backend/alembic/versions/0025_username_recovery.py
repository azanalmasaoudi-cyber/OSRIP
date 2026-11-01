"""Public registration by username and password, and one-time recovery codes (hash only).

Revision ID: 0025_username_recovery
Revises: 0024_datasets_reports
Create Date: 2026-11-01
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0025_username_recovery"
down_revision = "0024_datasets_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0025_username_recovery_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0025_username_recovery_down.sql")
