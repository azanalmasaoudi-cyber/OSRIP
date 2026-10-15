"""Approved-profile replies ('profile') and cancelled requests ('cancelled') as message
statuses; Al Mulhim profile version 2 (short hello and thanks replies) published and active.

Revision ID: 0014_mulhim_identity
Revises: 0013_assistant_profile
Create Date: 2026-10-08
"""

import json

import sqlalchemy as sa

from alembic import op
from app.db.sql_files import execute_sql_file

revision = "0014_mulhim_identity"
down_revision = "0013_assistant_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.assistant import profile

    bind = op.get_bind()
    execute_sql_file(bind, "0014_mulhim_identity_up.sql")
    second = profile.load_file(profile.profile_file(2))
    exists = bind.execute(
        sa.text("SELECT 1 FROM assistant_profile WHERE version = :v"), {"v": second.version}
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
            "version": second.version,
            "profile": json.dumps(profile.document(second), ensure_ascii=False),
            "sha": profile.checksum(second),
        },
    )


def downgrade() -> None:
    execute_sql_file(op.get_bind(), "0014_mulhim_identity_down.sql")
