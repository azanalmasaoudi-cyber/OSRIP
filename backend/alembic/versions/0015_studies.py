"""Stored study runs: validated parameters and the shared study result (tables, charts,
exports), with a checksum for reproduction.

Revision ID: 0015_studies
Revises: 0014_mulhim_identity
Create Date: 2026-10-08
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0015_studies"
down_revision = "0014_mulhim_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0015_studies_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0015_studies_down.sql")
