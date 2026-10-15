"""Accounts, authorization, import workflow, derived outputs and audit events.

Revision ID: 0003_accounts_imports
Revises: 0002_reference_seed
Create Date: 2026-09-25

Adds observation frequency and valuation basis, the synthetic-only commodity flag
(plus the SYNTH_COMMODITY fixture commodity), users/roles/permissions/sessions,
import_job/import_row, analysis runs, recommendations with append-only review
history, reports with frozen inputs, and append-only audit events.
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0003_accounts_imports"
down_revision = "0002_reference_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0003_accounts_imports_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0003_accounts_imports_down.sql")
