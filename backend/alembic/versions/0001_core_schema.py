"""Core reference, provenance and observation schema.

Revision ID: 0001_core_schema
Revises:
Create Date: 2026-09-24

The DDL lives in ``alembic/sql`` so the exact SQL can be reviewed and executed
directly with psql (see ``db_checks/``). SQLAlchemy models mirror this schema;
``alembic check`` must report no differences before a release.
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0001_core_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0001_core_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0001_core_down.sql")
