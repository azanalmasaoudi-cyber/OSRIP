"""Custom roles and user groups: a group gives its members roles and permissions.

Revision ID: 0026_groups_custom_roles
Revises: 0025_username_recovery
Create Date: 2026-11-01
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0026_groups_custom_roles"
down_revision = "0025_username_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0026_groups_custom_roles_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0026_groups_custom_roles_down.sql")
