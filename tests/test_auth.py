"""Phase 1 — logging in, the session cookie, and where the password ends up.

Four properties, and none of them is "the happy path works":

1. **A bad credential establishes nothing.** Not a 401 with a session attached, not
   a 401 that tells an attacker which half was wrong.
2. **The session cookie carries the attributes that make it a session cookie.**
   Single origin (ADR-0001) makes `SameSite` free, and free is not the same as set.
3. **The Hub is not public.** Only admin-created accounts get in, so the inventory
   endpoint refuses a caller with no session.
4. **The password is not in the database.** The one Phase 1 assertion that has to
   look past the HTTP boundary, because that is where the defect would live.

The credentials come from ``conftest.py`` and are deliberately unusual strings, so
the database scan in the last test cannot match a column name or a log line.
"""

from __future__ import annotations

import base64
import hashlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    HARDWARE_PATH,
    LOGIN_PATH,
    USER_EMAIL,
    USER_PASSWORD,
    USERS_PATH,
    attempt_login,
    issued_cookies,
)

UNKNOWN_EMAIL = "nobody.at.all@booksy.example"
WRONG_PASSWORD = "not-the-admin-password"


# --------------------------------------------------------------------------
# A rejected login establishes nothing
# --------------------------------------------------------------------------


def test_login_rejects_unknown_user(app, anonymous_client: TestClient) -> None:
    """An email with no account behind it cannot log in, whatever password it sends.

    The password used is **the real admin password**. That is the point: an
    implementation that looks up nothing and only compares the submitted password
    against every stored credential — or against a single configured one — would
    pass this test with a random string and fails it with this one.

    The second act is what makes the 401 mean something. A status code is a claim
    about what happened; the claim under test is that *no session exists*, so the
    same client is sent at an admin-only route afterwards. A route that returns 401
    and sets a session cookie anyway satisfies the first assertion and nothing else.
    """
    response = attempt_login(anonymous_client, UNKNOWN_EMAIL, ADMIN_PASSWORD)

    assert response.status_code == 401, (
        f"an unknown account must be refused with 401; POST {LOGIN_PATH} returned "
        f"{response.status_code}: {response.text}"
    )
    assert not issued_cookies(response), (
        "a refused login must not issue a cookie: the whole guard is worth nothing "
        "if the 401 arrives with a session attached; got "
        f"{issued_cookies(response)}"
    )
    assert UNKNOWN_EMAIL not in response.text, (
        "the refusal must not echo the submitted address back — a reflected value "
        f"is an injection surface as well as a hint; got {response.text!r}"
    )

    follow_up = anonymous_client.get(USERS_PATH)
    assert follow_up.status_code in (401, 403), (
        "the failed login must leave the client unauthenticated: an admin-only "
        f"route answered {follow_up.status_code} to a client whose only login "
        f"attempt was refused. Body: {follow_up.text}"
    )


def test_login_rejects_wrong_password(app, anonymous_client: TestClient) -> None:
    """A real account with the wrong password is refused, and indistinguishably so.

    Three acts, because the property is not just "wrong password fails":

    *Refusal* — 401, no cookie. *No enumeration* — the response is byte-identical to
    the one an unknown account gets, so the endpoint cannot be used to discover
    which addresses have accounts. That matters more here than usual: the deployed
    instance publishes demo credentials (ADR-0005), so the login form is the one
    endpoint a stranger is certain to reach.

    *Control, and it is not decoration* — the same account with the right password
    does log in. Without it, an endpoint that refuses every login on earth satisfies
    both assertions above, and this file's other tests would not notice either.
    """
    refused = attempt_login(anonymous_client, ADMIN_EMAIL, WRONG_PASSWORD)

    assert refused.status_code == 401, (
        f"an existing account with the wrong password must be refused with 401; "
        f"got {refused.status_code}: {refused.text}"
    )
    assert not issued_cookies(refused), (
        "a wrong password must not issue a session cookie; got "
        f"{issued_cookies(refused)}"
    )

    unknown = attempt_login(anonymous_client, UNKNOWN_EMAIL, WRONG_PASSWORD)
    assert (refused.status_code, refused.text) == (unknown.status_code, unknown.text), (
        "wrong password and unknown account must be indistinguishable, or the login "
        "endpoint enumerates accounts for anyone who asks twice: a real address "
        f"answered {refused.status_code} {refused.text!r} while an unknown one "
        f"answered {unknown.status_code} {unknown.text!r}"
    )

    accepted = attempt_login(anonymous_client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert accepted.status_code in (200, 204), (
        "control failed: the right password on the same account must succeed. "
        f"Got {accepted.status_code}: {accepted.text}. With login refusing "
        "everyone, the two assertions above prove nothing"
    )


# --------------------------------------------------------------------------
# The session cookie
# --------------------------------------------------------------------------
#
# Not in brainstorm.md §3's list, and added deliberately: §3's Phase 1 scope names
# "session cookie (same-site, free under single origin)" as a deliverable, and no
# named test touches it. ADR-0001's whole payoff for the auth layer is that
# `SameSite` costs nothing here — an untested payoff is an unclaimed one.
#
# It asserts attributes, not a cookie name and not a token format: those are the
# implementer's to choose, while `HttpOnly` and `SameSite` are the two things a
# browser acts on.


def test_session_cookie_is_http_only_and_same_site(
    app, anonymous_client: TestClient
) -> None:
    """A successful login issues a cookie a browser will protect.

    ``HttpOnly`` keeps the session out of ``document.cookie``, so an XSS in the Vue
    bundle cannot exfiltrate it. ``SameSite=Lax`` or ``Strict`` is what ADR-0001
    buys: on one origin there is no cross-site request that needs the cookie, so
    ``SameSite=None`` would be strictly worse and would drag CSRF handling back into
    scope.

    The last two assertions pin that the cookie *is* the credential rather than
    decoration beside some other mechanism: the client that received it reaches an
    admin-only route, and a client that did not is refused.
    """
    response = attempt_login(anonymous_client, ADMIN_EMAIL, ADMIN_PASSWORD)

    assert response.status_code in (200, 204), (
        f"setup: a valid login must succeed; got {response.status_code}: "
        f"{response.text}"
    )

    cookies = issued_cookies(response)
    assert cookies, (
        "a successful login must issue a session cookie — ADR-0001 chose "
        "cookie-based auth precisely because a single origin makes it cheap; no "
        f"Set-Cookie header was returned. Headers: {dict(response.headers)}"
    )

    attributes = "; ".join(cookies).lower()
    assert "httponly" in attributes, (
        "the session cookie must be HttpOnly, or any script in the bundle can read "
        f"the session out of document.cookie; got {cookies!r}"
    )
    assert "samesite=lax" in attributes or "samesite=strict" in attributes, (
        "the session cookie must declare SameSite=Lax or SameSite=Strict. Under "
        "single origin (ADR-0001) there is no cross-site request that needs it, so "
        "anything weaker — including leaving it unset — gives up protection that "
        f"costs nothing here; got {cookies!r}"
    )
    assert ADMIN_PASSWORD not in "; ".join(cookies), (
        "the cookie must not carry the credential it was exchanged for; got "
        f"{cookies!r}"
    )

    assert anonymous_client.get(USERS_PATH).status_code == 200, (
        "the cookie the client just received must actually authenticate it: an "
        "admin-only route refused the session it issued"
    )
    assert TestClient(app).get(USERS_PATH).status_code in (401, 403), (
        "a client without the cookie must be refused, or the route above was not "
        "authenticating anything"
    )


# --------------------------------------------------------------------------
# The Hub is not public
# --------------------------------------------------------------------------


def test_inventory_requires_a_session(app, anonymous_client: TestClient) -> None:
    """A caller with no session cannot read the inventory.

    **This test is the spec change.** `/api/hardware` was readable by anyone through
    Phase 0, and the brief allows only admin-created accounts into the Hub — an
    endpoint that hands the whole catalogue to a stranger with the URL contradicts
    that. Three Phase 0 tests were amended to authenticate as a consequence
    (`test_app.py`, and the reversal is recorded in `BACKLOG.md`). A decision that
    nothing asserts is decoration, so this is where it becomes real.

    **401 exactly, not 401-or-403.** Elsewhere in this suite an anonymous caller may
    be refused either way, because on a write route the distinction changes nothing a
    user sees. Here it does: this is the request the dashboard makes on first paint,
    and the Vue client uses the status to decide between showing the login screen and
    showing an error. A 403 there sends a signed-out employee to a dead end.

    The body matters as much as the status. A 401 that still serialises the catalogue
    into the error payload has leaked exactly what it refused.

    The control is second on purpose. Anonymous refusal is asserted first so this test
    fails on its own subject today rather than on a login endpoint that does not exist
    yet — but without the control, blanket-refusing `/api/hardware` would satisfy it
    while making the product inoperable.

    What must stay public is pinned next door: `test_serves_built_bundle_at_root`
    fetches `/` with no session, so an enforcement point that refuses everything —
    the tempting shape for a global middleware — turns that test red. Together they
    say the login page is reachable and nothing behind it is.
    """
    response = anonymous_client.get(HARDWARE_PATH)

    assert response.status_code == 401, (
        f"GET {HARDWARE_PATH} must refuse a caller with no session with 401: the Hub "
        "is for admin-created accounts only, and the Vue client needs 401 rather "
        f"than 403 to know to show the login screen. Got {response.status_code}: "
        f"{response.text[:200]}"
    )
    assert "purchase_date" not in response.text, (
        "the refusal must not carry the inventory in its body — a 401 that still "
        f"serialises the catalogue has leaked what it refused; got {response.text!r}"
    )

    signed_in = TestClient(app)
    admitted = attempt_login(signed_in, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert admitted.status_code in (200, 204), (
        "control setup: a valid login must succeed before this test can show that "
        f"the refusal above is about the session; got {admitted.status_code}: "
        f"{admitted.text}"
    )
    allowed = signed_in.get(HARDWARE_PATH)
    assert allowed.status_code == 200, (
        "control failed: a signed-in caller must be able to read the inventory. Got "
        f"{allowed.status_code}: {allowed.text}. An endpoint that refuses everyone "
        "satisfies the assertion above and ships an empty product"
    )
    assert allowed.json(), (
        "control failed: the signed-in read returned no items, so the 401 above "
        "cannot be attributed to the missing session"
    )


# --------------------------------------------------------------------------
# Where the password ends up
# --------------------------------------------------------------------------


def _stored_strings(database_path: Path) -> list[str]:
    """Every text value in every table, read straight out of the database file.

    Deliberately schema-agnostic. Asking ``app.storage`` for users would only prove
    what the read path chooses to return, and naming a ``users`` table would couple
    this test to a shape Phase 1 has not committed to yet. A plaintext password is a
    defect wherever it is written — a users table, an audit row, a session record —
    so the search covers all of them.
    """
    connection = sqlite3.connect(database_path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            )
        ]
        values: list[str] = []
        for table in tables:
            for row in connection.execute(f'select * from "{table}"'):
                for value in row:
                    if isinstance(value, str):
                        values.append(value)
                    elif isinstance(value, bytes):
                        values.append(value.decode("latin-1"))
    finally:
        connection.close()
    return values


def test_password_is_hashed_not_stored_plaintext(
    admin_client: TestClient, user_client: TestClient, database_path: Path
) -> None:
    """A created account's password is never recoverable from what was stored.

    ``user_client`` is requested rather than ignored, and it carries the two halves
    this test needs: the account was created through the admin API with a known
    password, **and** that password still logs in. Storage that mangles the
    credential beyond use would satisfy every assertion below, so "the password
    works" has to be part of the setup rather than an afterthought.

    The first assertion is a vacuity control. If nothing about the account reached
    the database at all — accounts held in memory, lost on restart — then "the
    password is not in the database" is true and worthless.

    Then the forbidden values. Plaintext is the named defect; hex and base64 are the
    same defect wearing a costume, and an unsalted digest is the version that looks
    like a fix. Each is checked separately so the failure message names which one
    was found. The scan also runs over the raw file bytes, which catches a value
    SQLite holds somewhere a ``SELECT`` does not reach.
    """
    stored = _stored_strings(database_path)

    assert any(USER_EMAIL in value for value in stored), (
        f"vacuity control: {USER_EMAIL} was created through the admin API but "
        "nothing in the database mentions it, so this test cannot tell a hashed "
        "password from an account that was never persisted. Accounts must survive "
        "a restart"
    )

    forbidden = {
        "the plaintext password": USER_PASSWORD,
        "the password hex-encoded": USER_PASSWORD.encode().hex(),
        "the password base64-encoded": base64.b64encode(
            USER_PASSWORD.encode()
        ).decode(),
        "an unsalted MD5 of the password": hashlib.md5(
            USER_PASSWORD.encode()
        ).hexdigest(),
        "an unsalted SHA-1 of the password": hashlib.sha1(
            USER_PASSWORD.encode()
        ).hexdigest(),
        "an unsalted SHA-256 of the password": hashlib.sha256(
            USER_PASSWORD.encode()
        ).hexdigest(),
    }

    for description, value in forbidden.items():
        assert not any(value in candidate for candidate in stored), (
            f"the database contains {description}. Passwords must be stored as a "
            "salted, deliberately slow digest — `hashlib.scrypt` or "
            "`hashlib.pbkdf2_hmac` are in the standard library — so that neither "
            "reversing nor a rainbow table recovers the credential from a database "
            "file. Note the database file itself is the thing committed to a "
            "persistent volume"
        )

    raw = database_path.read_bytes()
    assert USER_PASSWORD.encode() not in raw, (
        "the plaintext password appears in the database file's bytes even though no "
        "column returned it — a freed page, an index, or a table this scan read "
        "before the write landed. It is on disk either way"
    )

    listing = admin_client.get(USERS_PATH)
    assert listing.status_code == 200, (
        f"setup: an admin must be able to list accounts; got {listing.status_code}"
    )
    assert USER_PASSWORD not in listing.text, (
        "the account listing must not carry the password back over the wire; the "
        f"admin API returned it in {listing.text!r}"
    )
    assert ADMIN_PASSWORD not in listing.text, (
        "the bootstrapped admin's password must not appear in the account listing "
        "either — it comes from the environment, which makes echoing it a leak of "
        f"deployment configuration; got {listing.text!r}"
    )
