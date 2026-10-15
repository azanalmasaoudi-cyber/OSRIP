"""Password hashing and token primitives.

* Passwords: Argon2id via argon2-cffi (OWASP-recommended), default cost
  parameters of the library, automatic rehash when those parameters change.
* Session and CSRF tokens: 256-bit values from ``secrets``; only their SHA-256
  digests are stored, so a database leak does not expose live sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id

# A valid hash of an unguessable value, verified when an account does not exist
# so that response time does not reveal which e-mail addresses are registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

MIN_PASSWORD_LENGTH = 12
# A temporary password set by an operator only lets its holder choose a new password
# (the account has no permissions until then), so it may be shorter.
MIN_TEMPORARY_PASSWORD_LENGTH = 8
# Marker for service accounts: not a password and never matches one.
UNUSABLE_PASSWORD = "!"  # noqa: S105


def hash_password(password: str, *, temporary: bool = False) -> str:
    minimum = MIN_TEMPORARY_PASSWORD_LENGTH if temporary else MIN_PASSWORD_LENGTH
    if len(password) < minimum:
        raise ValueError(f"Password must be at least {minimum} characters.")
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Constant-work verification; unknown accounts and unusable hashes fail."""
    if not stored_hash or stored_hash == UNUSABLE_PASSWORD:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerificationError:
            pass
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return stored_hash != UNUSABLE_PASSWORD and _hasher.check_needs_rehash(stored_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def keyed_digest(key: str, value: str) -> str:
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def digests_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("ascii"), b.encode("ascii"))
