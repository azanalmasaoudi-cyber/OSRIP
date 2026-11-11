"""Usernames of 1 to 10 Arabic or English letters and digits; a key for uniqueness.

Revision ID: 0033_username_policy
Revises: 0032_wilayat_context
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0033_username_policy"
down_revision = "0032_wilayat_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0033_username_policy_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0033_username_policy_down.sql")
