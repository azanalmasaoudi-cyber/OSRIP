"""Who is acting. Every service call that changes data receives a Principal."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.domain.enums import Permission


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: uuid.UUID | None
    label: str  # e-mail, or 'anonymous'
    display_name: str = ""
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    session_id: uuid.UUID | None = None
    csrf_token_hash: str | None = None
    # A temporary password must be replaced first: until then the account holds no
    # permissions and may only change its password or sign out (migration 0011).
    password_change_required: bool = False

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    def has(self, permission: Permission) -> bool:
        return permission.value in self.permissions


ANONYMOUS = Principal(user_id=None, label="anonymous")
