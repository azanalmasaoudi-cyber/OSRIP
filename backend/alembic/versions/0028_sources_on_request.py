"""Sources on request: replies that list the previous answer's sources (status 'sources').

Revision ID: 0028_sources_on_request
Revises: 0027_session_remember
Create Date: 2026-11-02
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0028_sources_on_request"
down_revision = "0027_session_remember"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0028_sources_on_request_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0028_sources_on_request_down.sql")
