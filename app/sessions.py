"""The session cookie — turning a session token into a cookie value and back.

Signed, not encrypted: integrity is the requirement. The subject is a per-account
token issued once and never reissued, not the row id — a rowid is a storage detail
SQLite may lawfully reuse, and signing one made storage decisions into security
decisions (ADR-0013). Stateless; the trade-off is in BACKLOG.md.
"""

from __future__ import annotations

import hmac
from hashlib import sha256

__all__ = ["COOKIE_NAME", "issue", "subject_of", "cookie_kwargs"]

#: Prefixed so it cannot collide with anything the Vue bundle sets.
COOKIE_NAME = "hardware_hub_session"

_SEPARATOR = "."


def issue(session_token: str, secret_key: str) -> str:
    """The cookie value asserting ``session_token``, signed with ``secret_key``."""
    return f"{session_token}{_SEPARATOR}{_sign(session_token, secret_key)}"


def subject_of(cookie_value: str | None, secret_key: str) -> str | None:
    """The session token a cookie legitimately claims, or ``None``.

    ``None`` covers absent, malformed and mis-signed alike — the caller's response
    to all of them is identical, and a tampered cookie is not an outcome worth
    reporting to whoever tampered with it.
    """
    if not cookie_value:
        return None

    subject, separator, signature = cookie_value.rpartition(_SEPARATOR)
    # `token_urlsafe` never emits the separator; an empty subject is rejected
    # outright so a bare `.signature` cannot become a lookup for the token nobody has.
    if not separator or not subject:
        return None
    if not hmac.compare_digest(signature, _sign(subject, secret_key)):
        return None
    return subject


def cookie_kwargs(*, production: bool) -> dict[str, object]:
    """The session cookie's attributes.

    ``secure`` is conditional on purpose: unconditional, a local ``http://`` run
    silently never receives the cookie — the experience that teaches people to
    disable security flags. ``samesite="lax"`` is what single-origin pays for
    (ADR-0001).
    """
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": production,
        "path": "/",
    }


def _sign(subject: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), subject.encode("utf-8"), sha256).hexdigest()
