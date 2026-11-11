import uuid
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from app.domain.enums import AccountStatus, Permission, Role
from app.services import usernames

# A new or changed username: trimmed and normalised first, then at most 10 characters (the
# rest of the rule, and the reserved names, are checked by app/services/usernames.py).
NewUsername = Annotated[
    str,
    BeforeValidator(lambda v: usernames.normalize(v) if isinstance(v, str) else v),
    Field(min_length=1, max_length=usernames.MAX_LENGTH),
]
# The name typed to sign in or recover: also the longer names some accounts had before.
SignInUsername = Annotated[
    str,
    BeforeValidator(lambda v: usernames.normalize(v) if isinstance(v, str) else v),
    Field(min_length=1, max_length=usernames.LEGACY_MAX_LENGTH),
]


class LoginIn(BaseModel):
    # The username is the only sign-in name (no e-mail address or phone number).
    username: SignInUsername
    password: str = Field(min_length=1, max_length=1024)
    # Remember me: keep the session on this device; otherwise it ends with the browser.
    remember: bool = False


class UsernameRegisterIn(BaseModel):
    # No role, e-mail address or phone number can be given: new accounts are viewers.
    username: NewUsername
    password: str = Field(min_length=1, max_length=1024)
    password_confirm: str = Field(min_length=1, max_length=1024)


class RecoverIn(BaseModel):
    username: SignInUsername
    recovery_code: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=1, max_length=1024)
    new_password_confirm: str = Field(min_length=1, max_length=1024)


class RecoveryCodeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)


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
    has_recovery_code: bool | None = None  # never the code itself
    username: str | None = None
    password_change_required: bool = False
    roles: list[str] = []
    permissions: list[str] = []


class UserCreateIn(BaseModel):
    username: NewUsername
    display_name: str = Field(default="", max_length=200)
    password: str = Field(min_length=12, max_length=1024)
    roles: list[Role] = []


class UsernameIn(BaseModel):
    username: NewUsername


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
    service_account: bool = False  # no username, no password: never signs in


class RoleIn(BaseModel):
    role: str = Field(min_length=1, max_length=40)  # a built-in or custom role code


class GrantIn(BaseModel):
    permission: Permission
