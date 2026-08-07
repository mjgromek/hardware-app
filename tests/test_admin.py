"""Phase 1 — what an admin may do, and what everybody else may not.

Three of these four tests are refusals, which is the right ratio. "An admin can
delete hardware" is a feature; "a user cannot" is the product. Each refusal test
therefore carries a **control** in its last act — the same request, from an admin,
succeeding — because a route that refuses everyone satisfies every authorization
assertion ever written while shipping a broken feature.

Nothing here imports a dependency, a decorator or a middleware. The enforcement
point is `brainstorm.md` §7's open question; these tests only insist that the
request is refused, not on what refused it.

**`401` and `403` are not interchangeable.** An authenticated non-admin gets `403`:
it has a session, the session is not enough. Answering `401` there would tell the
Vue client to show a login form to somebody who is already logged in. Anonymous
callers are allowed either, since which one they see is not a product decision.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ANONYMOUS_REFUSAL,
    CREATED,
    DELETED,
    HARDWARE_PATH,
    UPDATED,
    USERS_PATH,
    accounts_by_email,
    attempt_login,
    statuses_by_id,
)

#: Seed id 1, the iPhone: `Available` and unflagged after ingestion, so it is a
#: legitimate target for both a delete and a Repair toggle.
TARGET_ITEM = 1

INTRUDER_EMAIL = "mallory@booksy.com"
INTRUDER_PASSWORD = "intruder-pw-8b22c5"

SECOND_ADMIN_EMAIL = "second.admin@booksy.com"
SECOND_ADMIN_PASSWORD = "second-admin-pw-1f90d4"


# --------------------------------------------------------------------------
# Account creation is admin-only
# --------------------------------------------------------------------------


def test_non_admin_cannot_create_user(
    app, user_client: TestClient, anonymous_client: TestClient
) -> None:
    """A `user`-role session cannot mint accounts, least of all admin accounts.

    The attempted account asks for ``role: "admin"``, because that is the request
    that matters: if a plain user can create accounts at all, they can create one
    with more privilege than they have and log into it. Privilege escalation, in one
    POST.

    ``403`` and not ``401``: this client is authenticated, and the Vue app has to be
    able to tell "log in" from "you may not".

    The second assertion is the one with teeth. A handler that creates the account
    and *then* decides to answer ``403`` passes a status-code-only test while having
    already done the damage, so the refusal is verified where it counts — the
    account must not be able to log in.

    The control lives in the ``user_client`` fixture: it exists only because an
    admin successfully created it through this same endpoint, so this test cannot
    pass against a ``POST /api/users`` that refuses everybody.
    """
    payload = {
        "email": INTRUDER_EMAIL,
        "password": INTRUDER_PASSWORD,
        "role": "admin",
    }

    response = user_client.post(USERS_PATH, json=payload)

    assert response.status_code == 403, (
        "a `user`-role session must be refused with 403 when creating an account — "
        "there is no self-registration and no self-promotion; POST "
        f"{USERS_PATH} returned {response.status_code}: {response.text}"
    )

    assert attempt_login(
        TestClient(app), INTRUDER_EMAIL, INTRUDER_PASSWORD
    ).status_code == 401, (
        f"the refused account must not exist: {INTRUDER_EMAIL} was able to log in "
        "after a 403, which means the handler wrote the row before it checked the "
        "role"
    )

    anonymous = anonymous_client.post(USERS_PATH, json=payload)
    assert anonymous.status_code in ANONYMOUS_REFUSAL, (
        "a caller with no session at all must be refused too — this is the request "
        f"a stranger with the public URL sends; got {anonymous.status_code}: "
        f"{anonymous.text}"
    )
    assert attempt_login(
        TestClient(app), INTRUDER_EMAIL, INTRUDER_PASSWORD
    ).status_code == 401, (
        "the anonymous attempt must not have created the account either"
    )


# --------------------------------------------------------------------------
# Hardware deletion is admin-only
# --------------------------------------------------------------------------


def test_non_admin_cannot_delete_hardware(
    user_client: TestClient, anonymous_client: TestClient, admin_client: TestClient
) -> None:
    """Only an admin removes inventory; a user's DELETE changes nothing.

    Both halves are asserted every time: the status code *and* that the item is
    still in the inventory afterwards. The dangerous mutation is not a wrong status
    code, it is a handler that deletes and then reports a refusal.

    The last act is the control, and it is also the only coverage Phase 1's "admin
    can delete hardware" gets: the identical request from an admin succeeds and the
    item is gone. Without it, ``return 403`` on every method satisfies this file.
    """
    before = statuses_by_id(admin_client)
    assert TARGET_ITEM in before, (
        f"setup: seed item {TARGET_ITEM} must be in the inventory to be deleted; "
        f"saw ids {sorted(before)}"
    )

    response = user_client.delete(f"{HARDWARE_PATH}/{TARGET_ITEM}")

    assert response.status_code == 403, (
        "a `user`-role session must be refused with 403 when deleting hardware; "
        f"DELETE {HARDWARE_PATH}/{TARGET_ITEM} returned {response.status_code}: "
        f"{response.text}"
    )
    assert statuses_by_id(admin_client) == before, (
        "the refused delete must leave the inventory untouched; the item is gone "
        "from the inventory even though the request was answered with 403"
    )

    anonymous = anonymous_client.delete(f"{HARDWARE_PATH}/{TARGET_ITEM}")
    assert anonymous.status_code in ANONYMOUS_REFUSAL, (
        "a caller with no session must be refused; got "
        f"{anonymous.status_code}: {anonymous.text}"
    )
    assert statuses_by_id(admin_client) == before, (
        "the anonymous delete must leave the inventory untouched either"
    )

    allowed = admin_client.delete(f"{HARDWARE_PATH}/{TARGET_ITEM}")
    assert allowed.status_code in DELETED, (
        "control failed: an admin must be able to delete hardware. Got "
        f"{allowed.status_code}: {allowed.text}. If deletion is refused for "
        "everyone, the refusals above prove nothing"
    )
    assert TARGET_ITEM not in statuses_by_id(admin_client), (
        f"control failed: item {TARGET_ITEM} is still in the inventory after an "
        "admin deleted it and the API reported success"
    )


# --------------------------------------------------------------------------
# The zero-admin invariant (ADR-0005)
# --------------------------------------------------------------------------


def test_cannot_remove_last_admin(app, admin_client: TestClient) -> None:
    """The last admin can be neither deleted nor demoted, and it is a `409`.

    **The status code is the whole point of pinning this at the HTTP boundary.**
    ADR-0005 says "at least one admin exists" is a guard in the same layer as the
    rental guards, returning ``409``. A ``403`` here would mean "you are not allowed
    to do this", which is false — an admin is allowed to delete admins. A ``400``
    would mean the request was malformed, which it is not. ``409 Conflict`` says the
    request is well-formed and permitted but would break an invariant, which is
    exactly what happened, and it is the same answer a rental against an item in
    ``Repair`` gets. Anything else means the guard was reimplemented somewhere else
    with different vocabulary.

    Both routes to zero admins are covered because either one alone leaves the
    lockout reachable: **delete** the account, or **demote** it to ``user``. Two
    clicks, and no account can ever be created again.

    Each refusal is verified by consequence, not by status code alone — the admin
    can still log in, and is still an admin.

    **The control is load-bearing.** ``409`` on every request to
    ``/api/users/{id}`` would satisfy the first two acts, and would also make
    account management entirely non-functional. So a second admin is created, then
    demoted (allowed — someone else is still an admin), then deleted (allowed). Both
    verbs are shown working, which is what makes the refusals above evidence of a
    guard rather than of a broken route.
    """
    accounts = accounts_by_email(admin_client)
    admins = [
        account for account in accounts.values() if account["role"] == "admin"
    ]
    assert len(admins) == 1, (
        "setup: ADR-0005 bootstraps exactly one admin from the environment, and "
        "this test is meaningless unless that admin is the last one; saw "
        f"{[(a['email'], a['role']) for a in accounts.values()]}"
    )
    last_admin_id = admins[0]["id"]

    # Act 1 — deleting the last admin is refused.
    deletion = admin_client.delete(f"{USERS_PATH}/{last_admin_id}")
    assert deletion.status_code == 409, (
        "removing the last admin must be refused with 409, through the same guard "
        "layer as the rental guards (ADR-0005) — not 403 (an admin is permitted to "
        "delete admins) and not 400 (the request is well-formed). Got "
        f"{deletion.status_code}: {deletion.text}"
    )
    assert "admin" in deletion.text.lower(), (
        "a guard returns 409 with a readable reason (CONTEXT.md); this one has to "
        "say that the last admin cannot be removed, or the UI has nothing to show "
        f"the person who tried; got {deletion.text!r}"
    )
    assert attempt_login(
        TestClient(app), ADMIN_EMAIL, ADMIN_PASSWORD
    ).status_code in (200, 204), (
        "the refused delete must leave the account usable: the last admin can no "
        "longer log in, so the row was removed before the guard ran and the system "
        "is already locked"
    )

    # Act 2 — demoting the last admin is the same lockout by another route.
    demotion = admin_client.patch(f"{USERS_PATH}/{last_admin_id}", json={"role": "user"})
    assert demotion.status_code == 409, (
        "demoting the last admin reaches zero admins exactly as deleting them "
        "does, and must be refused with 409 by the same guard; got "
        f"{demotion.status_code}: {demotion.text}"
    )
    assert accounts_by_email(admin_client)[ADMIN_EMAIL]["role"] == "admin", (
        "the refused demotion must leave the role alone; the last admin is now a "
        "`user`, which means no account can ever be created again"
    )

    # Act 3 — control: with a second admin present, both verbs work.
    created = admin_client.post(
        USERS_PATH,
        json={
            "email": SECOND_ADMIN_EMAIL,
            "password": SECOND_ADMIN_PASSWORD,
            "role": "admin",
        },
    )
    assert created.status_code in CREATED, (
        "control setup: an admin must be able to create a second admin; got "
        f"{created.status_code}: {created.text}"
    )
    second_admin_id = accounts_by_email(admin_client)[SECOND_ADMIN_EMAIL]["id"]

    demote_second = admin_client.patch(
        f"{USERS_PATH}/{second_admin_id}", json={"role": "user"}
    )
    assert demote_second.status_code in UPDATED, (
        "control failed: demoting an admin while another remains must be allowed — "
        "the guard protects the *last* admin, not admins in general. Got "
        f"{demote_second.status_code}: {demote_second.text}"
    )

    delete_second = admin_client.delete(f"{USERS_PATH}/{second_admin_id}")
    assert delete_second.status_code in DELETED, (
        "control failed: deleting an account that is not the last admin must be "
        f"allowed. Got {delete_second.status_code}: {delete_second.text}. With "
        "every write to /api/users/{id} answering 409, acts 1 and 2 would pass "
        "against an entirely broken route"
    )
    assert SECOND_ADMIN_EMAIL not in accounts_by_email(admin_client), (
        "control failed: the deleted account is still listed"
    )


# --------------------------------------------------------------------------
# Repair is an admin toggle, in both directions
# --------------------------------------------------------------------------


def test_admin_can_toggle_repair_status(admin_client: TestClient) -> None:
    """An admin moves one item into `Repair` and back, and nothing else moves.

    Both directions, because Phase 2's state diagram has both — ``Available →
    Repair`` and ``Repair → Available`` — and a one-way toggle strands every item an
    admin ever inspects. This is also the Phase 1 half of the machinery Phase 2's
    ``test_cannot_rent_hardware_in_repair`` will lean on: without a way in, that
    guard has nothing to guard.

    The blast-radius assertion is the discriminating one. "Item 1 is in Repair" is
    also true of an implementation that put *every* item in Repair, and of one that
    ignored the id in the path — both are plausible slips, and both would look right
    in a UI showing one row.

    The last act keeps the enum closed at the boundary. ``Status`` is exactly three
    values (CONTEXT.md), so an off-enum status must be refused as a malformed
    request rather than written — a fourth status in the database would break every
    guard that pattern-matches on the three.
    """
    before = statuses_by_id(admin_client)
    assert before.get(TARGET_ITEM) == "Available", (
        f"setup: seed item {TARGET_ITEM} should import as Available; got "
        f"{before.get(TARGET_ITEM)!r}"
    )

    into_repair = admin_client.patch(
        f"{HARDWARE_PATH}/{TARGET_ITEM}", json={"status": "Repair"}
    )
    assert into_repair.status_code in UPDATED, (
        f"an admin must be able to move an item into Repair; PATCH "
        f"{HARDWARE_PATH}/{TARGET_ITEM} returned {into_repair.status_code}: "
        f"{into_repair.text}"
    )

    after = statuses_by_id(admin_client)
    assert after.get(TARGET_ITEM) == "Repair", (
        f"item {TARGET_ITEM} must read as Repair once the toggle succeeded — the "
        "status a later request sees is the only one the rental guard will consult; "
        f"got {after.get(TARGET_ITEM)!r}"
    )
    collateral = {
        item_id: (was, after.get(item_id))
        for item_id, was in before.items()
        if item_id != TARGET_ITEM and was != after.get(item_id)
    }
    assert not collateral, (
        "the toggle must touch exactly the item named in the path — a handler that "
        "updates every row, or ignores the id, looks correct in a UI showing one "
        f"line. Changed elsewhere (id: before -> after): {collateral}"
    )

    back = admin_client.patch(
        f"{HARDWARE_PATH}/{TARGET_ITEM}", json={"status": "Available"}
    )
    assert back.status_code in UPDATED, (
        "an item must be releasable from Repair as well as sendable to it, or "
        f"every inspected item is stranded; got {back.status_code}: {back.text}"
    )
    assert statuses_by_id(admin_client) == before, (
        "toggling back must restore the inventory exactly as it was; got "
        f"{statuses_by_id(admin_client)} where {before} was expected"
    )

    off_enum = admin_client.patch(
        f"{HARDWARE_PATH}/{TARGET_ITEM}", json={"status": "Broken"}
    )
    assert off_enum.status_code in (400, 422), (
        "the status enum is exactly Available / In Use / Repair, so an off-enum "
        "value must be refused as a malformed request rather than stored; got "
        f"{off_enum.status_code}: {off_enum.text}"
    )
    assert statuses_by_id(admin_client)[TARGET_ITEM] == "Available", (
        "the refused status change must not have been written; item "
        f"{TARGET_ITEM} now reads "
        f"{statuses_by_id(admin_client)[TARGET_ITEM]!r}"
    )
