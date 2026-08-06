"""The session cookie — turning an account id into a cookie value and back.

Separate from ``app.accounts`` because it answers a different question. Accounts know
who exists; this knows how a browser carries the claim "I am account 3" so the server
can trust it without storing anything. Nothing here touches the database.

**Signed, not encrypted.** Integrity is the requirement: a client must not be able to
change the subject it presents. An HMAC over the subject with ``SECRET_KEY`` gives that,
in the standard library.

**The subject is a per-account token, not the row id.** It was the row id until
`/security-review` showed what that costs: `users.id` is a SQLite rowid alias, so
deleting the highest-id account frees its id, and the next account created inherits it —
along with every unexpired cookie naming it. A deleted `user`'s cookie became a live
admin's. A row id is a storage detail, and making it the session identity turned a
storage decision into a security one. Tokens are issued once and never reissued, so a
deleted account's cookie matches nothing, permanently.

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


def issue(session_token: str, secret_key: str) -> str:
    """The cookie value asserting ``session_token``, signed with ``secret_key``."""
    return f"{session_token}{_SEPARATOR}{_sign(session_token, secret_key)}"


def subject_of(cookie_value: str | None, secret_key: str) -> str | None:
    """The session token a cookie legitimately claims, or ``None``.

    ``None`` covers every way a cookie can fail to mean anything — absent, malformed,
    or signed with a different key — because the caller's response to all of them is
    identical: no session. A tampered cookie is not a distinct outcome worth
    reporting to whoever tampered with it.
    """
    if not cookie_value:
        return None

    subject, separator, signature = cookie_value.rpartition(_SEPARATOR)
    # `token_urlsafe` never emits the separator, so the split is unambiguous. An empty
    # subject is rejected outright rather than looked up, so a bare `.signature` cannot
    # become a query for the token nobody has.
    if not separator or not subject:
        return None
    if not hmac.compare_digest(signature, _sign(subject, secret_key)):
        return None
    return subject


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
