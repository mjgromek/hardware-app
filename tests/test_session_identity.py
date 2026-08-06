"""Phase 1 — who am I, for a client that has only a cookie.

The cookie is `HttpOnly`, so the Vue app cannot read the account out of it, and a
reload leaves the client holding a valid session it knows nothing about. Without a
route that answers this, the UI has to infer the role from whether an admin-only
request came back `403` — using an authorization failure as a data source, which means
a genuine permissions bug and a plain `user` account look identical.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, USER_EMAIL, USER_PASSWORD

SESSION_PATH = "/api/session"


def test_session_reports_the_signed_in_account(admin_client: TestClient) -> None:
    """A signed-in caller learns their own address and role, and no password."""
    response = admin_client.get(SESSION_PATH)

    assert response.status_code == 200, (
        f"a signed-in caller must be able to read their own session; GET "
        f"{SESSION_PATH} returned {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["email"] == ADMIN_EMAIL, (
        f"the session must name the account that holds it; got {body!r}"
    )
    assert body["role"] == "admin", (
        "the role is what the UI uses to decide whether to render admin controls; got "
        f"{body!r}"
    )
    assert ADMIN_PASSWORD not in response.text, (
        f"the session must not echo the credential it was exchanged for; got "
        f"{response.text!r}"
    )


def test_session_reports_a_plain_user_as_user(user_client: TestClient) -> None:
    """A `user` session reports `user` — the discriminating half.

    Without this, a handler hardcoding `"admin"` passes the test above, and every
    signed-in employee gets an admin panel rendered for them.
    """
    body = user_client.get(SESSION_PATH).json()

    assert (body["email"], body["role"]) == (USER_EMAIL, "user"), (
        f"a `user`-role session must report itself as `user`; got {body!r}"
    )
    assert USER_PASSWORD not in user_client.get(SESSION_PATH).text


def test_session_refuses_a_caller_without_one(anonymous_client: TestClient) -> None:
    """No session is `401`, which is the signal the client turns into a login screen."""
    response = anonymous_client.get(SESSION_PATH)

    assert response.status_code == 401, (
        "a caller with no session must get 401 here — this is the request the app "
        "makes on load to decide between the dashboard and the login screen, and "
        f"anything else strands it; got {response.status_code}: {response.text}"
    )
