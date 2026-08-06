"""Phase 1 — the cookie has to mean what it says.

`mvp-reviewer` found this gap by mutation: deleting the `hmac.compare_digest` check in
`app/sessions.py` left the whole suite green, because every test presented a cookie the
server had issued and none forged one. The signing code was correct; nothing defended it.

That matters more in Phase 2 than here. The wrong-user rental guard — "you cannot return
an item somebody else rented" — reduces entirely to trusting the account id in this
cookie. A forgeable cookie makes that guard decorative, and no rental test would notice.

These tests fail on the real implementation only if it is wrong, which is the point: each
one was confirmed to fail against a mutant that removes the check it exercises.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, HARDWARE_PATH, USERS_PATH, attempt_login

#: Must match the `SECRET_KEY` the `app` fixture boots with, or "the signature is wrong"
#: would be true for an uninteresting reason.
TEST_SECRET = "test-secret-key-not-the-real-one"

COOKIE_NAME = "hardware_hub_session"


def _sign(subject: str, secret: str) -> str:
    """Sign exactly as `app.sessions` does — an attacker who knows the scheme."""
    return hmac.new(secret.encode(), subject.encode(), sha256).hexdigest()


def test_tampered_session_cookie_is_refused(app, admin_client: TestClient) -> None:
    """A cookie the server did not issue authenticates nobody, however it is built.

    The old construction derived its "different subject" as `str(int(subject) + 1)`,
    which asserted the subject was an integer — the exact coupling the surrogate
    `session_token` was introduced to remove. Against a `token_urlsafe` subject that
    line raises `ValueError`, so the test was *broken* rather than failing. It is
    rebuilt here with no assumption about the subject's type at all: every forgery is
    string surgery on whatever the server handed out.

    Six forgeries, because they fail for different reasons and an implementation can
    stop one without stopping the others:

    1. **Signed with the wrong key** — the attacker knows the scheme and the subject
       but not `SECRET_KEY`. This is the one a missing `compare_digest` lets through.
    2. **A real signature moved onto a different subject** — the admin's own valid
       signature presented for an arbitrary subject string. Catches an implementation
       that checks a signature is well-formed, or present, rather than *for this
       subject*.
    3. **An empty subject, correctly signed** — the signature is genuinely valid for
       the empty string, so only an explicit refusal of an empty subject stops a bare
       `.signature` from becoming a lookup for the token nobody holds.
    4. **No signature at all.**
    5. **Subject only, no separator.**
    6. **A never-issued token, correctly signed with the real secret** — a fresh
       `secrets.token_urlsafe(32)` bearing an honest signature. This is the sharpest
       one and the one the old integer construction could not express: the signature
       check passes, so the only thing that can refuse it is the server resolving the
       subject against tokens it actually issued. An implementation that trusts a
       valid signature to imply a valid session accepts a stranger who has read
       `app/sessions.py` and knows `SECRET_KEY` is the only ingredient.

    The control is first: the same client with its real cookie reaches an admin route, so
    a server that refuses everyone cannot satisfy this test.
    """
    assert admin_client.get(USERS_PATH).status_code == 200, (
        "control: a genuine session must work, or the refusals below prove nothing"
    )

    genuine = admin_client.cookies.get(COOKIE_NAME)
    assert genuine, "control: the admin client must be holding a session cookie"
    genuine_subject, _, genuine_signature = genuine.rpartition(".")

    #: An arbitrary subject, not derived from the genuine one — the subject's type and
    #: structure are the server's business and nothing here may depend on them. It only
    #: has to be a subject the admin does not hold, or the "forgery" is the real cookie.
    other_subject = "not-a-subject-this-server-ever-issued"
    assert other_subject != genuine_subject, "the forged subject must differ from the real one"

    #: Well-formed, correctly signed, and never in the database.
    never_issued = secrets.token_urlsafe(32)

    forgeries = {
        "signed with a different key": f"{genuine_subject}.{_sign(genuine_subject, 'not-the-secret-key')}",
        "a real signature on another subject": f"{other_subject}.{genuine_signature}",
        "an empty subject, correctly signed": f".{_sign('', TEST_SECRET)}",
        "no signature": f"{genuine_subject}.",
        "no separator": genuine_subject,
        "a signature that is not hex": f"{genuine_subject}.not-a-signature",
        "a valid-format token that was never issued": f"{never_issued}.{_sign(never_issued, TEST_SECRET)}",
    }

    for description, forged in forgeries.items():
        client = TestClient(app)
        client.cookies.set(COOKIE_NAME, forged)

        for path in (USERS_PATH, HARDWARE_PATH):
            response = client.get(path)
            assert response.status_code == 401, (
                f"a cookie {description} must authenticate nobody: GET {path} answered "
                f"{response.status_code} to {forged!r}. A session is a subject the "
                "server issued *and* a signature it computed — either half alone is a "
                f"cookie a stranger can write. Body: {response.text[:200]}"
            )


def test_session_for_a_deleted_account_is_refused(app, admin_client: TestClient) -> None:
    """A correctly signed cookie for an account that no longer exists is refused.

    The signature proves the id was not tampered with. It does not prove the account is
    still there — `app/main.py`'s `current_account` docstring claims exactly this, and
    until now nothing checked it. Without the re-read, deleting an employee's account
    leaves their cookie working until it expires, and the cookie has no expiry.

    Built by creating a second admin, deleting it through the API, and presenting a cookie
    signed for its id. The signature is genuine; only the account is gone.
    """
    created = admin_client.post(
        USERS_PATH,
        json={"email": "temp.admin@booksy.example", "password": "temp-admin-pw-3e81f0", "role": "admin"},
    )
    assert created.status_code in (200, 201), (
        f"setup: an admin must be able to create the account this test deletes; got "
        f"{created.status_code}: {created.text}"
    )
    doomed_id = created.json()["id"]

    condemned = TestClient(app)
    assert attempt_login(
        condemned, "temp.admin@booksy.example", "temp-admin-pw-3e81f0"
    ).status_code in (200, 204), "setup: the new account must be able to log in"
    assert condemned.get(USERS_PATH).status_code == 200, (
        "setup: that session must work before it is invalidated, or this test cannot "
        "attribute the later refusal to the deletion"
    )

    removed = admin_client.delete(f"{USERS_PATH}/{doomed_id}")
    assert removed.status_code in (200, 204), (
        f"setup: deleting a non-last admin must be allowed; got {removed.status_code}"
    )

    for path in (USERS_PATH, HARDWARE_PATH):
        response = condemned.get(path)
        assert response.status_code == 401, (
            f"a session whose account was deleted must be refused: GET {path} answered "
            f"{response.status_code}. The signature is genuine and the account is gone — "
            "revoking access has to mean the session stops working"
        )

    forged = TestClient(app)
    forged.cookies.set(COOKIE_NAME, f"{doomed_id}.{_sign(str(doomed_id), TEST_SECRET)}")
    assert forged.get(USERS_PATH).status_code == 401, (
        "a correctly signed cookie naming a deleted account must still be refused — a "
        "valid signature over a dead id is not a session"
    )
