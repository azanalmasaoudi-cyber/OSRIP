"""Self-service accounts, external identities, mail outbox and the assistant.

Revision ID: 0006_identity_assistant
Revises: 0005_geography_forecasts
Create Date: 2026-09-25
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0006_identity_assistant"
down_revision = "0005_geography_forecasts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0006_identity_assistant_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0006_identity_assistant_down.sql")
