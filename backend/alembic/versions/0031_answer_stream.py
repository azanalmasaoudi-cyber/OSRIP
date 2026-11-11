"""The answer as it is written: 'answer.segment' and 'answer.reset' study events.

Revision ID: 0031_answer_stream
Revises: 0030_single_persona
Create Date: 2026-11-08
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0031_answer_stream"
down_revision = "0030_single_persona"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0031_answer_stream_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0031_answer_stream_down.sql")
