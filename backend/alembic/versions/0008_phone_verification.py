"""Registration and sign-in by phone (SMS verification); verified e-mail linking.

Revision ID: 0008_phone_verification
Revises: 0007_forecast_outputs_monitoring
Create Date: 2026-09-27
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0008_phone_verification"
down_revision = "0007_forecast_outputs_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0008_phone_verification_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0008_phone_verification_down.sql")
