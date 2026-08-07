"""`/security-review` — what deleting an account must not leave behind.

Three findings, all reachable through `DELETE /api/users/{id}`:

1. **SQLite recycles the id.** `users.id` is declared
   `Column(Integer, primary_key=True, autoincrement=True)`, which SQLAlchemy compiles
   for SQLite as a plain rowid alias with no `AUTOINCREMENT` keyword. Delete the
   highest row and the next insert is handed its id back.
2. **A recycled id revives a revoked session.** The cookie is signed over the id and
   nothing else (`app/sessions.py`), and `current_account` re-reads the account by that
   id — so once the id is occupied again, an unchanged cookie for the deleted account
   authenticates as *whoever holds it now*. If the replacement is an admin, a deleted
   `user` is a live admin. This is the escalation; `test_session_integrity.py` cannot
   see it, because it only ever checks the window while the id is vacant.
3. **An account can be deleted out from under its own rental.** `ensure_no_active_rental`
   already refuses moving a held item to `Repair` and deleting one (ADR-0009, ADR-0011);
   deleting the *renter* strands the same rental from the other end.

Every refusal is asserted by consequence as well as by status, and each test carries the
control that stops "refuse everything" from satisfying it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    CREATED,
    DELETED,
    HARDWARE_PATH,
    USER_EMAIL,
    USERS_PATH,
    accounts_by_email,
    attempt_login,
    audit_rows,
    clear_review_path,
    items_by_id,
    rent_path,
    return_path,
)

SESSION_PATH = "/api/session"
COOKIE_NAME = "hardware_hub_session"

#: Seed id 1, the iPhone: `Available` and unflagged, so a rental of it succeeds for
#: reasons that have nothing to do with this file.
RENTABLE_ITEM = 1

#: Seed id 6, flagged at import for a 2027 purchase date — the item an admin can clear,
#: which is an auditable action that needs no rental and so no rental guard.
FLAGGED_ITEM = 6


def _create_account(admin_client: TestClient, email: str, password: str, role: str) -> dict:
    response = admin_client.post(
        USERS_PATH, json={"email": email, "password": password, "role": role}
    )
    assert response.status_code in CREATED, (
        f"setup: an admin must be able to create {email}; POST {USERS_PATH} returned "
        f"{response.status_code}: {response.text}"
    )
    return response.json()


def _highest_account_id(admin_client: TestClient) -> int:
    return max(account["id"] for account in accounts_by_email(admin_client).values())


def test_deleted_account_id_is_never_reissued(admin_client: TestClient) -> None:
    """An id that has belonged to one account never belongs to another.

    The account is created last on purpose, so it holds the highest rowid — that is the
    only case SQLite recycles, and a test built on a middle id would pass while the hole
    stayed open.

    An account id is not an internal detail here: it is the entire content of the session
    cookie, it addresses `PATCH`/`DELETE /api/users/{id}`, and Phase 2 writes it into
    `rentals.account_id` and `audit_events`. Reusing one makes every one of those records
    ambiguous about which person it names.
    """
    doomed = _create_account(
        admin_client, "first.holder@booksy.example", "first-holder-pw-71c3a8", "user"
    )
    assert doomed["id"] == _highest_account_id(admin_client), (
        "setup: the account under test must hold the highest id, or SQLite would not "
        "recycle it and this test would pass without proving anything"
    )

    removed = admin_client.delete(f"{USERS_PATH}/{doomed['id']}")
    assert removed.status_code in DELETED, (
        f"setup: deleting a `user` account must be allowed; got {removed.status_code}: "
        f"{removed.text}"
    )

    replacement = _create_account(
        admin_client, "second.holder@booksy.example", "second-holder-pw-2f90d4", "user"
    )

    assert replacement["id"] != doomed["id"], (
        f"id {doomed['id']} belonged to first.holder@booksy.example and was handed "
        "straight back to second.holder@booksy.example. Ids must be issued once and "
        "never reused: the id is what a session cookie carries and what a rental row "
        "names, so a recycled one makes both point at a person who is gone"
    )


def test_audit_event_still_names_its_actor_after_that_account_is_deleted(
    app, admin_client: TestClient
) -> None:
    """Deleting an admin must not silently re-attribute what they did.

    An `audit_events` row carries `actor_account_id` alongside the snapshotted
    `actor_email` (ADR-0010). If a deleted account's id can be handed to the next
    account created, then every override that admin ever recorded quietly starts
    pointing at somebody else — and an audit trail that names the wrong person is worse
    than one that names nobody, because it reads as evidence. This is the same finding
    as the revived session, arriving through the table instead of through the cookie.

    The actor is a **second** admin holding nothing, because both other guards would
    otherwise take the delete first: the last admin cannot be deleted (ADR-0005) and an
    account with an active rental cannot be deleted either. `clear-review` is the
    auditable action for the same reason — it ends no rental, so the deleted actor
    leaves no rental behind to trip the second guard.

    Asserted by email *and* by id. The snapshot alone would pass against an
    implementation that recycles the id, and the id alone would pass against one that
    forgets who the person was; the row has to survive as a whole.
    """
    actor_email = "recording.admin@booksy.example"
    actor = _create_account(admin_client, actor_email, "recording-admin-pw-4b71fe", "admin")
    assert actor["id"] == _highest_account_id(admin_client), (
        "setup: the actor must hold the highest id, or deleting it frees nothing and "
        "the re-attribution this test looks for could not happen"
    )

    actor_client = TestClient(app)
    assert attempt_login(
        actor_client, actor_email, "recording-admin-pw-4b71fe"
    ).status_code in (200, 204), "setup: the second admin must be able to log in"

    cleared = actor_client.post(
        clear_review_path(FLAGGED_ITEM),
        json={"reason": "fixed: bench-tested by IT; the date was a data-entry error"},
    )
    assert cleared.status_code in (200, 201, 204), (
        f"setup: an admin must be able to clear a review flag; POST "
        f"{clear_review_path(FLAGGED_ITEM)} returned {cleared.status_code}: {cleared.text}"
    )

    events = audit_rows(app, action="clear_review_flag")
    assert len(events) == 1, (
        f"setup: clearing the flag must have written exactly one audit event; got {events}"
    )
    assert events[0]["actor_account_id"] == actor["id"], (
        f"setup: the event must name the admin who sent the request; got "
        f"{events[0]['actor_account_id']!r} against account {actor['id']}"
    )

    removed = admin_client.delete(f"{USERS_PATH}/{actor['id']}")
    assert removed.status_code in DELETED, (
        f"setup: a non-last admin holding no rental must be deletable; got "
        f"{removed.status_code}: {removed.text}"
    )

    successor = _create_account(
        admin_client, "successor@booksy.example", "successor-pw-90c2d7", "user"
    )

    after = audit_rows(app, action="clear_review_flag")
    assert len(after) == 1, (
        "deleting an account must not delete, duplicate or rewrite the events it "
        f"recorded — the override happened. Got {after}"
    )

    event = after[0]
    assert event["actor_email"] == actor_email, (
        f"the audit event no longer names {actor_email} as the admin who released item "
        f"{FLAGGED_ITEM}; got {event['actor_email']!r}. The email is snapshotted onto "
        "the row precisely so that deleting the account cannot erase who did it"
    )
    assert event["actor_account_id"] == actor["id"], (
        f"the event's actor id changed from {actor['id']} to "
        f"{event['actor_account_id']!r} when the account was deleted"
    )
    assert successor["id"] != event["actor_account_id"], (
        f"account id {event['actor_account_id']} recorded this override for "
        f"{actor_email}, and it has now been handed to successor@booksy.example. Anyone "
        f"joining `audit_events` to `users` reads that item {FLAGGED_ITEM} was cleared "
        "by a person who was not employed when it happened — the id an audit row names "
        "must belong to one account forever"
    )


def test_recycled_id_does_not_revive_a_session(app, admin_client: TestClient) -> None:
    """A revoked cookie stays revoked once its id is occupied again.

    The sequence is the exploit, in order:

    1. A `user` account is created, logs in, and its cookie is kept unchanged.
    2. The account is deleted. The cookie correctly `401`s — this intermediate
       assertion is what distinguishes "revoked" from "revoked, then revived", and
       without it the test could not tell the fix from a server that was never
       vulnerable in the window it checks.
    3. A replacement **admin** is created and, today, is issued the vacant id.
    4. The original, unchanged, never-re-signed cookie is replayed.

    The consequence is asserted, not only the status: the replayed cookie must not reach
    `GET /api/users`, which is admin-only. A deleted employee getting an admin listing
    back is the whole finding — the escalation does not need the attacker to do anything
    but keep a cookie they already had.
    """
    doomed = _create_account(
        admin_client, "departing@booksy.example", "departing-pw-58ab19", "user"
    )
    assert doomed["id"] == _highest_account_id(admin_client), (
        "setup: the deleted account must hold the highest id, or its id is not the one "
        "the next insert would be handed"
    )

    condemned = TestClient(app)
    assert attempt_login(
        condemned, "departing@booksy.example", "departing-pw-58ab19"
    ).status_code in (200, 204), "setup: the account must be able to log in"
    original_cookie = condemned.cookies.get(COOKIE_NAME)
    assert original_cookie, "setup: logging in must have issued a session cookie"

    removed = admin_client.delete(f"{USERS_PATH}/{doomed['id']}")
    assert removed.status_code in DELETED, (
        f"setup: deleting a `user` account must be allowed; got {removed.status_code}: "
        f"{removed.text}"
    )

    vacant = TestClient(app)
    vacant.cookies.set(COOKIE_NAME, original_cookie)
    assert vacant.get(SESSION_PATH).status_code == 401, (
        "control: while the id is vacant the deleted account's cookie must already be "
        "refused, or the revival below would be indistinguishable from a session that "
        "was never revoked at all"
    )

    _create_account(
        admin_client, "replacement.admin@booksy.example", "replacement-admin-pw-3d70ce", "admin"
    )

    replayed = TestClient(app)
    replayed.cookies.set(COOKIE_NAME, original_cookie)

    identity = replayed.get(SESSION_PATH)
    assert identity.status_code == 401, (
        "the deleted account's unchanged cookie authenticated somebody after a new "
        f"account took its id: GET {SESSION_PATH} answered {identity.status_code} with "
        f"{identity.text}. Revoking access has to be permanent — a departed employee "
        "must not come back as whoever was created next"
    )

    escalated = replayed.get(USERS_PATH)
    assert escalated.status_code == 401, (
        f"the replayed cookie reached the admin-only account listing: GET {USERS_PATH} "
        f"answered {escalated.status_code}. The cookie was issued to a deleted `user` "
        "and the id it names now belongs to an admin, so this is a deleted employee "
        f"reading and managing every account. Body: {escalated.text[:200]}"
    )


def test_cannot_delete_account_with_an_active_rental(
    app, admin_client: TestClient, user_client: TestClient
) -> None:
    """An account holding an item cannot be deleted; the item has to come back first.

    Same rule and same shape as `ensure_no_active_rental` already gives `delete_item`
    and the `Repair` toggle (ADR-0009, ADR-0011): a live rental is a fact about the
    world, and deleting either end of it leaves a row naming somebody who no longer
    exists — the laptop is still out, and nothing in the system says with whom.

    `409` and not `403`: an admin is permitted to delete accounts, and this one stops
    being refused the moment the item is returned. That is the same line ADR-0005 draws
    for the last admin.

    Refusal by consequence: the account is still listed, and the rental is still active
    and still theirs, read back from the renter's own `?held_by=me`. A handler that
    deletes and then answers `409` has already stranded the rental.

    The control is the same account after returning the item. Deleting it must then
    succeed, or "refuse every delete of anyone who ever rented anything" would satisfy
    everything above while making account management unusable.
    """
    claimed = user_client.post(rent_path(RENTABLE_ITEM))
    assert claimed.status_code in (200, 201, 204), (
        f"setup: an Available unflagged item must be rentable; POST "
        f"{rent_path(RENTABLE_ITEM)} returned {claimed.status_code}: {claimed.text}"
    )

    renter_id = accounts_by_email(admin_client)[USER_EMAIL]["id"]

    refusal = admin_client.delete(f"{USERS_PATH}/{renter_id}")

    assert refusal.status_code == 409, (
        f"deleting an account that holds an active rental must be refused with 409 — "
        f"the request is well-formed and an admin may delete accounts, but the rental "
        f"would be left pointing at nobody. DELETE {USERS_PATH}/{renter_id} returned "
        f"{refusal.status_code}: {refusal.text}"
    )
    assert USER_EMAIL in accounts_by_email(admin_client), (
        f"the refused delete removed {USER_EMAIL} anyway: a handler that deletes and "
        "then answers 409 has already done the damage the status code claims it "
        "prevented"
    )

    still_mine = user_client.get(HARDWARE_PATH, params={"held_by": "me"})
    assert still_mine.status_code == 200, (
        f"the refused delete must leave the renter's session working; GET "
        f"{HARDWARE_PATH}?held_by=me answered {still_mine.status_code}"
    )
    assert RENTABLE_ITEM in {item["id"] for item in still_mine.json()}, (
        f"item {RENTABLE_ITEM} is no longer held by {USER_EMAIL} after the refused "
        "delete — the rental has to survive a refusal intact, not be quietly closed"
    )
    assert items_by_id(admin_client)[RENTABLE_ITEM]["assigned_to"] == USER_EMAIL, (
        f"item {RENTABLE_ITEM} must still be assigned to {USER_EMAIL} after the "
        "refused delete; got "
        f"{items_by_id(admin_client)[RENTABLE_ITEM]['assigned_to']!r}"
    )

    returned = user_client.post(return_path(RENTABLE_ITEM))
    assert returned.status_code in (200, 201, 204), (
        f"setup: a renter must be able to return their own item; POST "
        f"{return_path(RENTABLE_ITEM)} returned {returned.status_code}: {returned.text}"
    )

    allowed = admin_client.delete(f"{USERS_PATH}/{renter_id}")
    assert allowed.status_code in DELETED, (
        f"control failed: with the item returned there is no active rental, so this "
        f"account must be deletable. DELETE {USERS_PATH}/{renter_id} returned "
        f"{allowed.status_code}: {allowed.text}. If every delete is refused, the 409 "
        "above is a broken route rather than a guard"
    )

