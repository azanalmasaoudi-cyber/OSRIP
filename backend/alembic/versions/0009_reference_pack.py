"""Curated reference pack: provenance fields, statement records, reporting groups,
indicator hierarchy, explicit unit conversions and documented data-quality notes.

Revision ID: 0009_reference_pack
Revises: 0008_phone_verification
Create Date: 2026-09-28
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0009_reference_pack"
down_revision = "0008_phone_verification"
branch_labels = None
depends_on = None

# New enum values must be committed before any statement may use them.
ENUM_VALUES = (
    "ALTER TYPE observation_frequency ADD VALUE IF NOT EXISTS 'statement'",
    "ALTER TYPE area_level ADD VALUE IF NOT EXISTS 'reporting_group'",
    "ALTER TYPE physical_dimension ADD VALUE IF NOT EXISTS 'area'",
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for statement in ENUM_VALUES:
            op.execute(statement)
    execute_sql_file(op.get_bind(), "0009_reference_pack_up.sql")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values; the three added values stay defined but unused.
    execute_sql_file(op.get_bind(), "0009_reference_pack_down.sql")
