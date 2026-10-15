"""Assistant modes and structured replies, research papers as a source class, saved
research, indicator watchlists and data-update / threshold alerts.

Revision ID: 0012_research_library
Revises: 0011_username_research
Create Date: 2026-10-05
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0012_research_library"
down_revision = "0011_username_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0012_research_library_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0012_research_library_down.sql")
