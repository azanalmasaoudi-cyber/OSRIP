"""Provider call log: outcome, time, tokens and estimated cost of each call to an external AI
or search provider (no prompts or answers), for readiness and spending limits.

Revision ID: 0018_provider_calls
Revises: 0017_assistant_personas
Create Date: 2026-10-10
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0018_provider_calls"
down_revision = "0017_assistant_personas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0018_provider_calls_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0018_provider_calls_down.sql")
