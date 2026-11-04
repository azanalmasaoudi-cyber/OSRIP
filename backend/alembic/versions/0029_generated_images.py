"""Generated illustrations (generated_image) and the 'image' provider capability.

Revision ID: 0029_generated_images
Revises: 0028_sources_on_request
Create Date: 2026-11-03
"""

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0029_generated_images"
down_revision = "0028_sources_on_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), "0029_generated_images_up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0029_generated_images_down.sql")
