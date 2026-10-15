"""Indicator limitation texts and frozen report content.

Revision ID: 0004_analysis_reports
Revises: 0003_accounts_imports
Create Date: 2026-09-26
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0004_analysis_reports"
down_revision = "0003_accounts_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0004_analysis_reports_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0004_analysis_reports_down.sql")
