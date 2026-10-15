"""Usernames and required password changes for operator-created accounts; the review
queue for statistics found by web research.

Revision ID: 0011_username_research
Revises: 0010_guest_allowance
Create Date: 2026-10-02
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0011_username_research"
down_revision = "0010_guest_allowance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0011_username_research_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0011_username_research_down.sql")
