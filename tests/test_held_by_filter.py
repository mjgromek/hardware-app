"""Phase 2 slice C — `GET /api/hardware?held_by=me`, the My Rentals filter.

`docs/specs/phase-2.md` settles the shape: no new endpoint, one filter on the route the
dashboard already calls. A separate `/api/rentals/mine` would duplicate the serialiser
ADR-0012 just made role-dependent, and the duplicate is the copy that forgets.

Written by the implementer rather than `test-author` because the route is Slice C and the
red pass covered A and B. New file, so nothing in the existing suite is touched.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    HARDWARE_PATH,
    USER_EMAIL,
    items_by_id,
    rent_path,
)

#: Seed id 1 and 4: `Available`, unflagged, rentable without a guard firing.
FIRST_ITEM = 1
SECOND_ITEM = 4

#: Seed id 7, held at import by an address with no account (ADR-0007).
SEED_HELD_ITEM = 7


def _held_by_me(client: TestClient) -> dict[int, dict]:
    response = client.get(HARDWARE_PATH, params={"held_by": "me"})
    assert response.status_code == 200, (
        f"GET {HARDWARE_PATH}?held_by=me must serve the caller's own rentals; got "
        f"{response.status_code}: {response.text}"
    )
    return {item["id"]: item for item in response.json()}


def test_held_by_me_returns_only_my_rentals(
    user_client: TestClient, other_user_client: TestClient
) -> None:
    """The filter is scoped to the caller, and it is scoped by *account*.

    Two employees rent two different items, and each sees exactly their own. The second
    renter is what makes this discriminating: a filter implemented as "every item that is
    `In Use`" passes with one renter and hands one employee's rentals to another as soon
    as there are two. That is a data-leak-shaped bug, not a display bug.

    Seed id 7 is the third control. It is held, by nobody with an account, so it must
    appear in neither employee's list — an implementation matching on
    `assigned_to IS NOT NULL` would show it to both.
    """
    assert _held_by_me(user_client) == {}, (
        "setup: an employee holding nothing sees nothing — an empty list, not the "
        "whole inventory"
    )

    assert user_client.post(rent_path(FIRST_ITEM)).status_code in (200, 201), "setup"
    assert other_user_client.post(rent_path(SECOND_ITEM)).status_code in (200, 201), "setup"

    mine = _held_by_me(user_client)
    theirs = _held_by_me(other_user_client)

    assert set(mine) == {FIRST_ITEM}, (
        f"the filter must return exactly what this caller holds; got {sorted(mine)}"
    )
    assert set(theirs) == {SECOND_ITEM}, (
        f"and the other employee sees only theirs; got {sorted(theirs)}. A filter on "
        "`status = 'In Use'` rather than on the caller's account hands one employee's "
        "rentals to another"
    )
    assert SEED_HELD_ITEM not in mine and SEED_HELD_ITEM not in theirs, (
        f"seed item {SEED_HELD_ITEM} is held by an address with no account (ADR-0007) "
        "and belongs to neither of them"
    )
    assert mine[FIRST_ITEM]["assigned_to"] == USER_EMAIL, (
        "the returned row still carries the renter, because ADR-0012 keeps renter "
        f"identity visible; got {mine[FIRST_ITEM].get('assigned_to')!r}"
    )


def test_held_by_me_empties_when_the_item_comes_back(user_client: TestClient) -> None:
    """Returning an item removes it from the list. The obvious half, and it can break.

    A filter reading `rentals` without the `ended_at IS NULL` condition keeps every item
    the employee has *ever* held, so My Rentals grows forever and shows returned
    equipment as outstanding.
    """
    assert user_client.post(rent_path(FIRST_ITEM)).status_code in (200, 201), "setup"
    assert set(_held_by_me(user_client)) == {FIRST_ITEM}, "setup"

    returned = user_client.post(f"{HARDWARE_PATH}/{FIRST_ITEM}/return")
    assert returned.status_code in (200, 201, 204), (
        f"setup: the renter must be able to return their own item; got {returned.status_code}"
    )

    assert _held_by_me(user_client) == {}, (
        "a returned item is no longer held, so it leaves My Rentals. A filter that "
        "ignores `ended_at` shows every item the employee ever had"
    )


def test_held_by_accepts_only_me(user_client: TestClient, admin_client: TestClient) -> None:
    """`?held_by=` is not a way to read somebody else's rentals.

    `me` is the only accepted value — closed like `status` and `sort` are, for the same
    reason. An open parameter taking an email would let any signed-in employee enumerate
    what a named colleague is holding, which is a different feature with a different
    authorization question, and Phase 2 has not asked it.
    """
    assert user_client.post(rent_path(FIRST_ITEM)).status_code in (200, 201), "setup"

    for value in (USER_EMAIL, "1", "all", "everyone"):
        response = user_client.get(HARDWARE_PATH, params={"held_by": value})
        assert response.status_code in (400, 422), (
            f"?held_by={value!r} must be refused as malformed rather than interpreted; "
            f"got {response.status_code}: {response.text[:160]}"
        )

    assert set(items_by_id(admin_client)) != {FIRST_ITEM}, (
        "control: the unfiltered inventory is still the whole inventory"
    )
