"""Forecast future estimates and captured application errors.

Revision ID: 0007_forecast_outputs_monitoring
Revises: 0006_identity_assistant
Create Date: 2026-09-26
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0007_forecast_outputs_monitoring"
down_revision = "0006_identity_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0007_forecast_outputs_monitoring_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0007_forecast_outputs_monitoring_down.sql")
