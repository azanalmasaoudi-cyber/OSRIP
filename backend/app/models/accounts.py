import uuid
from datetime import datetime

from sqlalchemy import CHAR, Boolean, DateTime, ForeignKey, Identity, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import AccountStatus
from app.models.types import ACCOUNT_STATUS

UUID_PK = {"primary_key": True, "server_default": text("gen_random_uuid()")}
NOW = {"server_default": func.now()}


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    # None for phone-only accounts (migration 0008).
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[AccountStatus] = mapped_column(ACCOUNT_STATUS, server_default=text("'active'"))
    is_service_account: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_via: Mapped[str] = mapped_column(Text, server_default=text("'administrator'"))
    phone_e164: Mapped[str | None] = mapped_column(Text)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Operator-created accounts may be identified by a username alone (migration 0011).
    username: Mapped[str | None] = mapped_column(Text)
    password_change_required: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # The assistant persona this person chose (a code from the active profile; migration 0017).
    # NULL: the profile's default persona.
    assistant_persona: Mapped[str | None] = mapped_column(Text)


class RoleRow(Base):
    __tablename__ = "role"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text)


class PermissionRow(Base):
    __tablename__ = "permission"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_code: Mapped[str] = mapped_column(ForeignKey("role.code"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permission.code"), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    role_code: Mapped[str] = mapped_column(ForeignKey("role.code"), primary_key=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class UserPermissionGrant(Base):
    __tablename__ = "user_permission_grant"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(ForeignKey("permission.code"), primary_key=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(CHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempt"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text)
    client_hash: Mapped[str] = mapped_column(CHAR(64))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class AuthToken(Base):
    """Single-use, expiring e-mail token (verification, recovery, magic link)."""

    __tablename__ = "auth_token"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Target address of a link_email token (None for every other purpose).
    email: Mapped[str | None] = mapped_column(Text)


class PhoneChallenge(Base):
    """One SMS verification series for one number. The code is held by the provider only."""

    __tablename__ = "phone_challenge"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    phone_e164: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    provider_ref: Mapped[str] = mapped_column(Text)
    client_hash: Mapped[str] = mapped_column(CHAR(64))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalIdentity(Base):
    __tablename__ = "external_identity"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    issuer: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OidcRequest(Base):
    __tablename__ = "oidc_request"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    provider: Mapped[str] = mapped_column(Text)
    state_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    browser_hash: Mapped[str] = mapped_column(CHAR(64))
    nonce: Mapped[str] = mapped_column(Text)
    code_verifier: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailOutbox(Base):
    """Development mail sink (never written by the SMTP backend)."""

    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    to_address: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
