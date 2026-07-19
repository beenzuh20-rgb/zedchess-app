"""
Small security / formatting helpers used across the app.
"""

import re

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
_EMAIL_ON = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_username(username: str) -> bool:
    return bool(username) and bool(_USERNAME_RE.match(username))


def basic_email_check(email: str) -> bool:
    return bool(email) and bool(_EMAIL_ON.match(email))


def sanitize_text(value: str, max_len: int = 1000) -> str:
    """Trim and clamp user-supplied text. Template auto-escaping handles XSS;
    this guards length and stray control characters."""
    if not value:
        return ""
    value = value.replace("\x00", "")
    return value.strip()[:max_len]


def format_money(amount: float) -> str:
    return f"{amount:,.2f}"


def allowed_avatar(filename: str, allowed: set) -> bool:
    if not filename:
        return False
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in allowed
