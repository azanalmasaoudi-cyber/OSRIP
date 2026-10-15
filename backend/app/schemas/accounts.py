import uuid

from pydantic import BaseModel, Field

from app.domain.enums import AccountStatus, Permission, Role


class LoginIn(BaseModel):
    # The sign-in identifier: an e-mail address or a username (field name kept for
    # compatibility with existing clients).
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class MeOut(BaseModel):
    authenticated: bool
    user_id: uuid.UUID | None = None
    email: str | None = None
    display_name: str | None = None
    email_verified: bool | None = None
    phone: str | None = None  # masked, e.g. "+968 ••••••67"
    phone_verified: bool | None = None
    has_password: bool | None = None
    username: str | None = None
    password_change_required: bool = False
    roles: list[str] = []
    permissions: list[str] = []


class UserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)
    roles: list[Role] = []


class UserOut(BaseModel):
    id: uuid.UUID
    email: str | None
    phone: str | None = None  # masked
    display_name: str
    status: AccountStatus
    roles: list[str]
    grants: list[str]
    email_verified: bool = False
    created_via: str = "administrator"
    username: str | None = None


class RoleIn(BaseModel):
    role: Role


class GrantIn(BaseModel):
    permission: Permission
