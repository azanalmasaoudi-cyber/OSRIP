"""Research candidates from 2021 onward, as the platform's statistical scope.

Revision ID: 0034_candidate_scope_2021
Revises: 0033_username_policy
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0034_candidate_scope_2021"
down_revision = "0033_username_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0034_candidate_scope_2021_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0034_candidate_scope_2021_down.sql")
