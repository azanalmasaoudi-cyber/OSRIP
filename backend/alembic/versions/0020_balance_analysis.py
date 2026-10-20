"""Shortage and surplus analyses: stored as study runs of kind ``supply_balance`` with their
own validated document (osrip.balance/1).

Revision ID: 0020_balance_analysis
Revises: 0019_study_events
Create Date: 2026-10-20
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0020_balance_analysis"
down_revision = "0019_study_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0020_balance_analysis_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0020_balance_analysis_down.sql")
