"""Sourced governorate and wilayat registry; forecast prediction records.

Revision ID: 0005_geography_forecasts
Revises: 0004_analysis_reports
Create Date: 2026-09-25
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0005_geography_forecasts"
down_revision = "0004_analysis_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0005_geography_forecasts_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0005_geography_forecasts_down.sql")
