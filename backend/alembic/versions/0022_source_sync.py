"""Official statistics feeds: the registry of publication series OSRIP follows, the releases
found in them, and the log of each check (run by the separate sync worker).

Revision ID: 0022_source_sync
Revises: 0021_research_workflow
Create Date: 2026-10-23
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0022_source_sync"
down_revision = "0021_research_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0022_source_sync_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0022_source_sync_down.sql")
