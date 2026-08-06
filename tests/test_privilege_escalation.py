"""Phase 1 — a `user` cannot become an admin, by any route it can reach.

`mvp-reviewer`: "privilege-escalation routes are guarded but unasserted". Only
`admin_client` ever called `PATCH`/`DELETE /api/users`, so the guards on them were correct
by inspection and pinned by nothing.

The distinction matters for what these tests are worth. They are not fixing a hole — the
`Depends(current_admin)` on those routes already refuses a `user`, and that is verified
below by consequence rather than by reading the source. They exist so that removing or
loosening the dependency turns the suite red, which is what a guard needs in order to
still be there in Phase 3.

Every assertion checks the *consequence*, not the status code: after each refusal the
account's role is re-read, because a handler that writes and then answers `403` passes a
status-only test having already escalated.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    ANONYMOUS_REFUSAL,
    HARDWARE_PATH,
    USER_EMAIL,
    USERS_PATH,
    accounts_by_email,
    attempt_login,
)


def _role_of(admin_client: TestClient, email: str) -> str:
    return accounts_by_email(admin_client)[email]["role"]


def test_non_admin_cannot_promote_itself(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """The one request that matters most: a `user` promoting its own account.

    If this succeeds, every other guard in the system is irrelevant — one `PATCH` and the
    caller owns the inventory, the account list, and the ability to mint more admins.

    `own_id` is discovered the way an attacker would have to: it is not secret (it is in
    the admin listing, and account ids are small sequential integers), so the test simply
    reads it and uses it. Guessing it is not the barrier; the role check is.
    """
    own_id = accounts_by_email(admin_client)[USER_EMAIL]["id"]

    response = user_client.patch(f"{USERS_PATH}/{own_id}", json={"role": "admin"})

    assert response.status_code == 403, (
        "a `user` session must be refused with 403 when changing its own role — this is "
        f"privilege escalation in one request; PATCH {USERS_PATH}/{own_id} returned "
        f"{response.status_code}: {response.text}"
    )
    assert _role_of(admin_client, USER_EMAIL) == "user", (
        "the refused promotion must not have been written: the account is now an admin "
        "even though the API answered 403, which means the handler wrote the row before "
        "it checked the role"
    )
    assert user_client.get(USERS_PATH).status_code == 403, (
        "and the session must still be a `user` session afterwards — if the role changed "
        "in the database, an admin-only route would now admit it"
    )


def test_non_admin_cannot_reach_the_other_admin_routes(
    app, user_client: TestClient, anonymous_client: TestClient, admin_client: TestClient
) -> None:
    """Every remaining admin route refuses a `user` and an anonymous caller.

    `test_admin.py` covers account creation and hardware deletion. These are the four it
    does not: listing accounts, deleting an account, changing an item's status, and adding
    hardware from a `user` session. A guard missing from any one of them is a hole — the
    account list is an enumeration of every employee, and `PATCH /api/hardware` lets a
    plain user strand equipment in `Repair`.

    Anonymous callers may get `401` or `403`; which one is not a product decision. An
    authenticated `user` must get `403` exactly, or the Vue client shows a login form to
    somebody who is already signed in.
    """
    own_id = accounts_by_email(admin_client)[USER_EMAIL]["id"]

    forbidden = {
        f"GET {USERS_PATH}": lambda c: c.get(USERS_PATH),
        f"DELETE {USERS_PATH}/{own_id}": lambda c: c.delete(f"{USERS_PATH}/{own_id}"),
        f"PATCH {HARDWARE_PATH}/1": lambda c: c.patch(f"{HARDWARE_PATH}/1", json={"status": "Repair"}),
        f"POST {HARDWARE_PATH}": lambda c: c.post(HARDWARE_PATH, json={"name": "Smuggled Laptop"}),
    }

    for description, call in forbidden.items():
        assert call(user_client).status_code == 403, (
            f"{description} must answer 403 to a `user` session"
        )
        assert call(anonymous_client).status_code in ANONYMOUS_REFUSAL, (
            f"{description} must refuse a caller with no session"
        )

    # Consequences, not just codes: nothing above may have taken effect.
    assert USER_EMAIL in accounts_by_email(admin_client), (
        "the refused DELETE must not have removed the account"
    )
    assert attempt_login(TestClient(app), "Smuggled Laptop", "irrelevant").status_code == 401
    inventory = admin_client.get(HARDWARE_PATH).json()
    assert not any(item["name"] == "Smuggled Laptop" for item in inventory), (
        "the refused POST must not have added an item"
    )
    assert next(item for item in inventory if item["id"] == 1)["status"] == "Available", (
        "the refused PATCH must not have moved item 1 into Repair"
    )
