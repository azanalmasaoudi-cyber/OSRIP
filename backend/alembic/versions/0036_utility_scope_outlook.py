"""A utility's own reporting scope (Nama Water Services) with its two operational water measures,
and the official outlook (forecasts, targets, plans) kept apart from observations, each item with
its evidence class and a review status.

Revision ID: 0036_utility_scope_outlook
Revises: 0035_honey_production
Create Date: 2026-11-24
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0036_utility_scope_outlook"
down_revision = "0035_honey_production"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0036_utility_scope_outlook_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0036_utility_scope_outlook_down.sql")
