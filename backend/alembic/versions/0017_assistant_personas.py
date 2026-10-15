"""Two selectable assistant personas: each person's choice and the persona of each reply;
assistant profile version 3 (Al Mulhim and Ilham) published and active.

Revision ID: 0017_assistant_personas
Revises: 0016_request_progress
Create Date: 2026-10-10
"""

import json

import sqlalchemy as sa

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0017_assistant_personas"
down_revision = "0016_request_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.assistant import profile

    bind = op.get_bind()
    execute_sql_file(bind, "0017_assistant_personas_up.sql")
    third = profile.load_file(profile.profile_file(3))
    exists = bind.execute(
        sa.text("SELECT 1 FROM assistant_profile WHERE version = :v"), {"v": third.version}
    ).scalar()
    if exists:  # already published with the CLI
        return
    bind.execute(
        sa.text(
            "UPDATE assistant_profile SET status = 'retired', retired_at = now() "
            "WHERE status = 'active'"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO assistant_profile (version, status, profile, content_sha256, activated_at)"
            " VALUES (:version, 'active', CAST(:profile AS jsonb), :sha, now())"
        ),
        {
            "version": third.version,
            "profile": json.dumps(profile.document(third), ensure_ascii=False),
            "sha": profile.checksum(third),
        },
    )


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0017_assistant_personas_down.sql")
