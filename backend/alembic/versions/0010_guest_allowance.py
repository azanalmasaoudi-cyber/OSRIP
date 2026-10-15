"""Five-answer guest allowance: guest sessions, idempotent assistant requests with
reservations, guest-owned conversations and the labelled non-AI lookup reply.

Revision ID: 0010_guest_allowance
Revises: 0009_reference_pack
Create Date: 2026-09-30
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0010_guest_allowance"
down_revision = "0009_reference_pack"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0010_guest_allowance_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0010_guest_allowance_down.sql")
