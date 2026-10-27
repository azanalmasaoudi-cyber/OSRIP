"""Datasets people upload to analyse (CSV, Excel, JSON; private to their owner), research and
dataset reports frozen at creation, and the dataset.analyze permission.

Revision ID: 0024_datasets_reports
Revises: 0023_research_save
Create Date: 2026-10-26
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0024_datasets_reports"
down_revision = "0023_research_save"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0024_datasets_reports_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0024_datasets_reports_down.sql")
