"""The session cookie — turning an account id into a cookie value and back.

Separate from ``app.accounts`` because it answers a different question. Accounts know
who exists; this knows how a browser carries the claim "I am account 3" so the server
can trust it without storing anything. Nothing here touches the database.

**Signed, not encrypted.** The account id is not a secret — it is in every admin
listing — so confidentiality buys nothing and integrity is the whole requirement: a
client must not be able to change the id it presents. An HMAC over the id with
``SECRET_KEY`` gives exactly that, in the standard library.

Stateless, which is a real trade-off recorded in ``BACKLOG.md``: there is no server
side to invalidate, so logout can only clear the cookie and a leaked one stays valid
until ``SECRET_KEY`` changes. Session expiry is not in Phase 1's scope.
"""

from __future__ import annotations

import hmac
from hashlib import sha256

__all__ = ["COOKIE_NAME", "issue", "subject_of", "cookie_kwargs"]

#: Prefixed so it cannot collide with anything the Vue bundle sets.
COOKIE_NAME = "hardware_hub_session"

_SEPARATOR = "."


def issue(account_id: int, secret_key: str) -> str:
    """The cookie value asserting ``account_id``, signed with ``secret_key``."""
    subject = str(account_id)
    return f"{subject}{_SEPARATOR}{_sign(subject, secret_key)}"


def subject_of(cookie_value: str | None, secret_key: str) -> int | None:
    """The account id a cookie legitimately claims, or ``None``.

    ``None`` covers every way a cookie can fail to mean anything — absent, malformed,
    or signed with a different key — because the caller's response to all of them is
    identical: no session. A tampered cookie is not a distinct outcome worth
    reporting to whoever tampered with it.
    """
    if not cookie_value:
        return None

    subject, separator, signature = cookie_value.rpartition(_SEPARATOR)
    if not separator or not subject.isdigit():
        return None
    if not hmac.compare_digest(signature, _sign(subject, secret_key)):
        return None
    return int(subject)


def cookie_kwargs(*, production: bool) -> dict[str, object]:
    """The attributes the session cookie is set with.

    ``httponly`` keeps the session out of ``document.cookie``, so an XSS in the
    bundle cannot read it. ``samesite="lax"`` is what ADR-0001 pays for: on one
    origin no cross-site request needs the cookie, so ``None`` would give up CSRF
    protection that costs nothing here.

    ``secure`` is conditional and that is not a shortcut. Railway serves the
    deployment over HTTPS, so production sets it; a local ``http://127.0.0.1`` run
    would silently never receive the cookie if it were unconditional, which is a
    development experience that teaches people to disable security flags.
    """
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": production,
        "path": "/",
    }


def _sign(subject: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), subject.encode("utf-8"), sha256).hexdigest()
