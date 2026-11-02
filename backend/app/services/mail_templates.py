"""Account e-mails in Arabic and English: a plain-text body and an HTML alternative.

Every message carries both languages, the reader's own first (the language of the page
the request came from). The HTML is a single centred card with inline styles (what mail
clients render reliably), the Arabic part right to left, a button and the same link as
plain text for clients that hide buttons. Values are escaped; a message never contains a
script, a tracking pixel or an external image, and a link is only the one the person
asked for.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

BRAND = "#047857"  # the site's primary colour (emerald)
INK = "#18181b"
MUTED = "#55555d"
BORDER = "#e2e2e6"
PAGE = "#f5f5f6"

# kind -> language -> parts. {name}, {hours}, {minutes}, {address} and {phone} are filled in.
TEXTS: dict[str, dict[str, dict[str, str]]] = {
    "verify_email": {
        "en": {
            "subject": "Confirm your OSRIP e-mail address",
            "title": "Confirm your e-mail address",
            "greeting": "Hello {name},",
            "body": "Press the button to confirm this address for your OSRIP account. The link works once and is valid for {hours} hours.",
            "button": "Confirm e-mail address",
            "ignore": "If you did not create an account, ignore this message.",
        },
        "ar": {
            "subject": "تأكيد بريدك الإلكتروني في OSRIP",
            "title": "تأكيد بريدك الإلكتروني",
            "greeting": "مرحباً {name}،",
            "body": "اضغط الزر لتأكيد هذا العنوان لحسابك في OSRIP. يعمل الرابط مرة واحدة وهو صالح لمدة {hours} ساعة.",
            "button": "تأكيد البريد الإلكتروني",
            "ignore": "إذا لم تنشئ حساباً فتجاهل هذه الرسالة.",
        },
    },
    "account_exists": {
        "en": {
            "subject": "OSRIP: an account already exists",
            "title": "An account already exists",
            "greeting": "Hello,",
            "body": "Someone asked to use this address for an OSRIP account, but it already belongs to one. Sign in, or use “Forgot password”.",
            "button": "Sign in",
            "ignore": "If this was not you, no action is needed.",
        },
        "ar": {
            "subject": "OSRIP: يوجد حساب بالفعل",
            "title": "يوجد حساب بالفعل",
            "greeting": "مرحباً،",
            "body": "طلب أحدهم استخدام هذا العنوان لحساب في OSRIP، لكنه مرتبط بحساب بالفعل. سجّل الدخول، أو استخدم «نسيت كلمة المرور».",
            "button": "تسجيل الدخول",
            "ignore": "إن لم تكن أنت فلا حاجة لأي إجراء.",
        },
    },
    "reset_password": {
        "en": {
            "subject": "Reset your OSRIP password",
            "title": "Reset your password",
            "greeting": "Hello {name},",
            "body": "A password reset was requested for your OSRIP account. Choose a new password within {minutes} minutes; the link works once. Every device signed in to your account will be signed out.",
            "button": "Choose a new password",
            "ignore": "If you did not ask for this, ignore this message; your password stays unchanged.",
        },
        "ar": {
            "subject": "إعادة تعيين كلمة المرور في OSRIP",
            "title": "إعادة تعيين كلمة المرور",
            "greeting": "مرحباً {name}،",
            "body": "طُلبت إعادة تعيين كلمة المرور لحسابك في OSRIP. اختر كلمة مرور جديدة خلال {minutes} دقيقة؛ يعمل الرابط مرة واحدة. سيُسجَّل الخروج من كل جهاز داخل إلى حسابك.",
            "button": "اختيار كلمة مرور جديدة",
            "ignore": "إن لم تطلب ذلك فتجاهل هذه الرسالة؛ تبقى كلمة مرورك كما هي.",
        },
    },
    "magic_link": {
        "en": {
            "subject": "Your OSRIP sign-in link",
            "title": "Sign in to OSRIP",
            "greeting": "Hello {name},",
            "body": "Press the button within {minutes} minutes to sign in. The link works once.",
            "button": "Sign in",
            "ignore": "If you did not ask for it, ignore this message.",
        },
        "ar": {
            "subject": "رابط الدخول إلى OSRIP",
            "title": "الدخول إلى OSRIP",
            "greeting": "مرحباً {name}،",
            "body": "اضغط الزر خلال {minutes} دقيقة لتسجيل الدخول. يعمل الرابط مرة واحدة.",
            "button": "تسجيل الدخول",
            "ignore": "إن لم تطلبه فتجاهل هذه الرسالة.",
        },
    },
    "link_email": {
        "en": {
            "subject": "Add this e-mail address to OSRIP",
            "title": "Add this e-mail address",
            "greeting": "Hello {name},",
            "body": "Press the button to add this address to your OSRIP account. The link works once and is valid for {hours} hours.",
            "button": "Add e-mail address",
            "ignore": "If you did not ask for this, ignore this message.",
        },
        "ar": {
            "subject": "إضافة هذا البريد إلى OSRIP",
            "title": "إضافة هذا البريد الإلكتروني",
            "greeting": "مرحباً {name}،",
            "body": "اضغط الزر لإضافة هذا العنوان إلى حسابك في OSRIP. يعمل الرابط مرة واحدة وهو صالح لمدة {hours} ساعة.",
            "button": "إضافة البريد الإلكتروني",
            "ignore": "إن لم تطلب ذلك فتجاهل هذه الرسالة.",
        },
    },
    "change_email": {
        "en": {
            "subject": "Confirm your new OSRIP e-mail address",
            "title": "Confirm your new e-mail address",
            "greeting": "Hello {name},",
            "body": "Press the button to make this the e-mail address of your OSRIP account. The link works once and is valid for {hours} hours. Your current address will be told about the change.",
            "button": "Confirm new address",
            "ignore": "If you did not ask for this, ignore this message; nothing changes.",
        },
        "ar": {
            "subject": "تأكيد بريدك الإلكتروني الجديد في OSRIP",
            "title": "تأكيد بريدك الإلكتروني الجديد",
            "greeting": "مرحباً {name}،",
            "body": "اضغط الزر ليصبح هذا العنوان بريد حسابك في OSRIP. يعمل الرابط مرة واحدة وهو صالح لمدة {hours} ساعة. سيُبلَّغ عنوانك الحالي بهذا التغيير.",
            "button": "تأكيد العنوان الجديد",
            "ignore": "إن لم تطلب ذلك فتجاهل هذه الرسالة؛ لن يتغير شيء.",
        },
    },
    "email_changed": {
        "en": {
            "subject": "Your OSRIP e-mail address was changed",
            "title": "Your e-mail address was changed",
            "greeting": "Hello {name},",
            "body": "The e-mail address of your OSRIP account was changed to {address}. Messages about your account now go there.",
            "button": "Reset your password",
            "ignore": "If you did not make this change, reset your password at once and contact an administrator.",
        },
        "ar": {
            "subject": "تغيّر بريدك الإلكتروني في OSRIP",
            "title": "تغيّر بريدك الإلكتروني",
            "greeting": "مرحباً {name}،",
            "body": "تغيّر البريد الإلكتروني لحسابك في OSRIP إلى {address}. تصل رسائل حسابك إليه من الآن.",
            "button": "إعادة تعيين كلمة المرور",
            "ignore": "إن لم تجرِ هذا التغيير فأعد تعيين كلمة المرور فوراً وتواصل مع المسؤول.",
        },
    },
    "phone_changed": {
        "en": {
            "subject": "Your OSRIP phone number was changed",
            "title": "Your phone number was changed",
            "greeting": "Hello {name},",
            "body": "The verified phone number of your OSRIP account was changed to {phone}.",
            "button": "Open your account",
            "ignore": "If you did not make this change, sign in, check your account and contact an administrator.",
        },
        "ar": {
            "subject": "تغيّر رقم هاتفك في OSRIP",
            "title": "تغيّر رقم هاتفك",
            "greeting": "مرحباً {name}،",
            "body": "تغيّر رقم الهاتف المؤكَّد لحسابك في OSRIP إلى {phone}.",
            "button": "فتح حسابك",
            "ignore": "إن لم تجرِ هذا التغيير فسجّل الدخول وراجع حسابك وتواصل مع المسؤول.",
        },
    },
}
COMMON = {
    "en": {
        "fallback": "If the button does not work, open this link:",
        "footer": "OSRIP sent this message because of a request on your account.",
    },
    "ar": {
        "fallback": "إذا لم يعمل الزر فافتح هذا الرابط:",
        "footer": "أرسل OSRIP هذه الرسالة بسبب طلب على حسابك.",
    },
}


@dataclass(frozen=True, slots=True)
class Rendered:
    subject: str
    text: str
    html: str


def _order(language: str) -> tuple[str, str]:
    return ("ar", "en") if language == "ar" else ("en", "ar")


def _section_html(lang: str, parts: dict[str, str], link: str | None) -> str:
    rtl = lang == "ar"
    align = "right" if rtl else "left"
    button = ""
    if link:
        href = escape(link, quote=True)
        button = (
            f'<p style="margin:24px 0"><a href="{href}" style="background:{BRAND};color:#ffffff;'
            "text-decoration:none;padding:12px 22px;border-radius:8px;display:inline-block;"
            f'font-weight:600">{escape(parts["button"])}</a></p>'
            f'<p style="margin:0 0 12px;font-size:13px;color:{MUTED}">{escape(COMMON[lang]["fallback"])}<br>'
            f'<a href="{href}" dir="ltr" style="color:{BRAND};word-break:break-all">{escape(link)}</a></p>'
        )
    return (
        f'<tr><td dir="{"rtl" if rtl else "ltr"}" lang="{lang}" style="padding:24px 28px;'
        f'text-align:{align};border-top:1px solid {BORDER}">'
        f'<h1 style="margin:0 0 12px;font-size:20px;line-height:1.4;color:{INK}">{escape(parts["title"])}</h1>'
        f'<p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:{INK}">{escape(parts["greeting"])}</p>'
        f'<p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:{INK}">{escape(parts["body"])}</p>'
        f"{button}"
        f'<p style="margin:12px 0 0;font-size:13px;line-height:1.6;color:{MUTED}">{escape(parts["ignore"])}</p>'
        "</td></tr>"
    )


def render(kind: str, language: str, *, link: str | None = None, **values: object) -> Rendered:
    """The message ``kind`` in both languages, ``language`` first."""
    first, second = _order(language)
    filled = {
        lang: {
            k: v.format(**{key: str(val) for key, val in values.items()})
            for k, v in TEXTS[kind][lang].items()
        }
        for lang in (first, second)
    }
    subject = f"{filled[first]['subject']} / {filled[second]['subject']}"
    text_parts = []
    for lang in (first, second):
        p = filled[lang]
        lines = [p["title"], "", p["greeting"], "", p["body"]]
        if link:
            lines += ["", f"{p['button']}: {link}"]
        lines += ["", p["ignore"]]
        text_parts.append("\n".join(lines))
    text = (
        "\n\n----\n\n".join(text_parts)
        + f"\n\n{COMMON[first]['footer']}\n{COMMON[second]['footer']}\n"
    )
    sections = "".join(_section_html(lang, filled[lang], link) for lang in (first, second))
    html = (
        "<!doctype html>"
        f'<html lang="{first}" dir="{"rtl" if first == "ar" else "ltr"}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(subject)}</title></head>"
        f"<body style=\"margin:0;padding:0;background:{PAGE};font-family:'Segoe UI',Tahoma,Arial,sans-serif\">"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE};padding:24px 12px">'
        '<tr><td align="center">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;'
        f'border:1px solid {BORDER};border-radius:12px;border-collapse:separate;overflow:hidden">'
        f'<tr><td style="background:{BRAND};padding:16px 28px;color:#ffffff;font-size:18px;font-weight:700;'
        'letter-spacing:0.5px">OSRIP</td></tr>'
        f"{sections}"
        f'<tr><td style="padding:16px 28px;border-top:1px solid {BORDER};font-size:12px;line-height:1.6;color:{MUTED}">'
        f'<span dir="ltr">{escape(COMMON["en"]["footer"])}</span><br>'
        f'<span dir="rtl" lang="ar">{escape(COMMON["ar"]["footer"])}</span></td></tr>'
        "</table></td></tr></table></body></html>"
    )
    return Rendered(subject, text, html)
