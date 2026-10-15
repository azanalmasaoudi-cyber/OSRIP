"""Al Mulhim's versioned identity and approved project knowledge (assistant_profile),
with version 1 from backend/app/knowledge/assistant_profile_v1.json.

Revision ID: 0013_assistant_profile
Revises: 0012_research_library
Create Date: 2026-10-08
"""

import json

import sqlalchemy as sa

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0013_assistant_profile"
down_revision = "0012_research_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.assistant import profile

    bind = op.get_bind()
    execute_sql_file(bind, "0013_assistant_profile_up.sql")
    first = profile.load_file(profile.profile_file(1))
    bind.execute(
        sa.text(
            "INSERT INTO assistant_profile (version, status, profile, content_sha256, activated_at)"
            " VALUES (:version, 'active', CAST(:profile AS jsonb), :sha, now())"
        ),
        {
            "version": first.version,
            "profile": json.dumps(profile.document(first), ensure_ascii=False),
            "sha": profile.checksum(first),
        },
    )


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0013_assistant_profile_down.sql")
