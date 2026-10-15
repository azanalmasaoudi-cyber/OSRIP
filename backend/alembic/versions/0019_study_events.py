"""Live study events: each real step of an assistant study (stage, source, search outcome,
validated dataset, partial failure, completion with findings and narration), streamed to the
person asking and replayable later.

Revision ID: 0019_study_events
Revises: 0018_provider_calls
Create Date: 2026-10-10
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0019_study_events"
down_revision = "0018_provider_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0019_study_events_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0019_study_events_down.sql")
