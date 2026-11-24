"""Honey production by governorate: the indicator and the kilogram unit the Statistical Year
Book 2026 (Table 4-5) publishes it in.

Revision ID: 0035_honey_production
Revises: 0034_candidate_scope_2021
Create Date: 2026-11-23
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0035_honey_production"
down_revision = "0034_candidate_scope_2021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0035_honey_production_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0035_honey_production_down.sql")
