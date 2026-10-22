"""Research workflow: the data-based report status for replies given without AI
interpretation when the answer service fails, background study jobs with their steps and
retrieved documents, and scheduled reports (off by default).

Revision ID: 0021_research_workflow
Revises: 0020_balance_analysis
Create Date: 2026-10-21
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0021_research_workflow"
down_revision = "0020_balance_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0021_research_workflow_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0021_research_workflow_down.sql")
