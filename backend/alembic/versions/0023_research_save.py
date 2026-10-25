"""Research that saves verified figures: the search log and cache, documents read outside a
study with their text, candidates mapped to platform codes with their validation and history,
data-update jobs and schedules, and the research.submit permission.

Revision ID: 0023_research_save
Revises: 0022_source_sync
Create Date: 2026-10-25
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0023_research_save"
down_revision = "0022_source_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0023_research_save_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0023_research_save_down.sql")
