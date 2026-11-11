"""Population by wilayat as context, and commercial registrations: the indicators and units the
November 2026 wilayat evidence review needs.

Revision ID: 0032_wilayat_context
Revises: 0031_answer_stream
Create Date: 2026-11-09
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0032_wilayat_context"
down_revision = "0031_answer_stream"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A new enum value can be used only after it is committed: added on its own first.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE section_code ADD VALUE IF NOT EXISTS 'population'")
    execute_sql_file(op.get_bind(), "0032_wilayat_context_up.sql")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value; 'population' stays, unused, after the rows go.
    execute_sql_file(op.get_bind(), "0032_wilayat_context_down.sql")
