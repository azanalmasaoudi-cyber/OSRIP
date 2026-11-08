"""One assistant persona: assistant profile version 4 (Al Mulhim only) published and active.
Ilham is retired from the interface; earlier replies keep the persona they were given and each
person's saved choice is left as it is (an unknown choice falls back to Al Mulhim).

Revision ID: 0030_single_persona
Revises: 0029_generated_images
Create Date: 2026-11-08
"""

import json

import sqlalchemy as sa

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0030_single_persona"
down_revision = "0029_generated_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.assistant import profile

    bind = op.get_bind()
    fourth = profile.load_file(profile.profile_file(4))
    exists = bind.execute(
        sa.text("SELECT 1 FROM assistant_profile WHERE version = :v"), {"v": fourth.version}
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
            "version": fourth.version,
            "profile": json.dumps(profile.document(fourth), ensure_ascii=False),
            "sha": profile.checksum(fourth),
        },
    )


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0030_single_persona_down.sql")
