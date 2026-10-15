"""Visible progress stages and cancellation for assistant requests; a cancelled request
is never charged.

Revision ID: 0016_request_progress
Revises: 0015_studies
Create Date: 2026-10-08
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0016_request_progress"
down_revision = "0015_studies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0016_request_progress_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0016_request_progress_down.sql")
