"""The username rule (migration 0033): 1 to 10 characters, Arabic or English letters and digits.

* Surrounding spaces are removed, the name is NFKC-normalised (Arabic presentation forms and
  full-width letters become ordinary letters) and Arabic-Indic digits become 0-9.
* Letters of one script only: English letters, or Arabic letters (no diacritics or tatweel).
  Digits may follow, and ``_``, ``.`` or ``-`` may be used; none is required. The first
  character is a letter.
* Uniqueness ignores case and the spelling variants that make two Arabic names look alike
  (alef with or without hamza, final ya and alef maqsura, ta marbuta and ha): ``key``.
* Names that could pass for the platform, its assistant or its staff are reserved, also with
  digits or punctuation added (``admin1``, ``Azzan_``).

The database applies the same length and characters to every new or changed username
(trigger ``trg_app_user_username_policy``). Usernames accounts already had before 0033 are
left as they are and keep working: sign-in looks names up by ``key`` without the length rule.
"""

from __future__ import annotations

import re
import unicodedata

from app.core.errors import ApiError, unprocessable

MAX_LENGTH = 10
# Sign-in and recovery accept the longer names some accounts had before the rule (up to 32).
LEGACY_MAX_LENGTH = 64

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "0123456789" * 2)
LATIN = "A-Za-z"
# Arabic letters: hamza to ghain, fa to ya, and the extended letters (no tatweel U+0640,
# no diacritics U+064B-U+065F, no Arabic punctuation).
ARABIC = "\u0621-\u063a\u0641-\u064a\u066e\u066f\u0671-\u06d3"
TAIL = "0-9_.-"
PATTERN = re.compile(rf"[{LATIN}][{LATIN}{TAIL}]*|[{ARABIC}][{ARABIC}{TAIL}]*")

_FOLD = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه"}
)

_RESERVED = (
    "admin", "administrator", "root", "system", "support", "osrip", "security", "moderator",
    "owner", "staff", "help", "service", "official", "ncsi", "azzan", "guest", "api",
    "mulhim", "almulhim", "ilham",
    "مدير", "المدير", "ادمن", "مسؤول", "المسؤول", "النظام", "نظام", "الدعم", "دعم", "المالك",
    "الإدارة", "اداره", "عزان", "الملهم", "ملهم", "إلهام", "رسمي",
)  # fmt: skip


def normalize(raw: str) -> str:
    """The name as stored: NFKC, Arabic-Indic digits as 0-9, without surrounding spaces."""
    return unicodedata.normalize("NFKC", raw).translate(_DIGITS).strip()


def key(raw: str) -> str:
    """What uniqueness and sign-in compare: the normalised name, lower case, with Arabic
    look-alike letters folded. For an English name it is simply the name in lower case."""
    return normalize(raw).lower().translate(_FOLD)


def _skeleton(name_key: str) -> str:
    """The key without punctuation and trailing digits, for the reserved-name check."""
    return re.sub(r"[_.\-]", "", name_key).rstrip("0123456789")


RESERVED = frozenset(_skeleton(key(name)) for name in _RESERVED)


def is_reserved(raw: str) -> bool:
    return _skeleton(key(raw)) in RESERVED


def problem(raw: str, *, allow_reserved: bool = False) -> ApiError | None:
    """Why a new username is refused, or None. ``allow_reserved`` is for the operator's own
    commands (``ensure-admin --username Azzan``), never for registration."""
    name = normalize(raw)
    if not name:
        return unprocessable("username_required", "Enter a username.")
    if len(name) > MAX_LENGTH:
        return unprocessable(
            "username_too_long", f"Username must not exceed {MAX_LENGTH} characters."
        )
    if not PATTERN.fullmatch(name):
        return unprocessable(
            "invalid_username",
            "Use Arabic or English letters and digits, starting with a letter "
            "(you may add _ . or -).",
        )
    if not allow_reserved and is_reserved(name):
        return unprocessable("username_reserved", "This username is reserved. Choose another.")
    return None
