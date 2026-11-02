"""Remember me: a persistent session the person chose on this device.

Revision ID: 0027_session_remember
Revises: 0026_groups_custom_roles
Create Date: 2026-11-02
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0027_session_remember"
down_revision = "0026_groups_custom_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0027_session_remember_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0027_session_remember_down.sql")
