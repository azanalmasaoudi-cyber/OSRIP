"""Definitional reference rows (units, indicators, national area, provisional commodities).

Revision ID: 0002_reference_seed
Revises: 0001_core_schema
Create Date: 2026-09-24

No observations or statistics are inserted by migrations.
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0002_reference_seed"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0002_reference_seed_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0002_reference_seed_down.sql")
