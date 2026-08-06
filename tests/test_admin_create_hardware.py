"""Phase 1 — adding hardware, which §3 listed as scope and never gave a test.

`brainstorm.md` §3 names "Admin: add / delete hardware, toggle Repair, create
accounts" but its nine tests cover only the last three. The wireframes have an "Add
New Device" button, so the UI needs the route; a route with no test is production code
without a spec, which this project does not ship.

Written as a separate module rather than added to `test_admin.py`: that file is
`test-author`'s and its four tests are green. Nothing here may soften them.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import CREATED, HARDWARE_PATH, statuses_by_id

NEW_ITEM = {"name": "Framework Laptop 13", "brand": "Framework", "purchase_date": "2026-03-01"}


def test_admin_can_add_hardware(admin_client: TestClient) -> None:
    """A created item joins the inventory as `Available` and unflagged.

    The status is asserted rather than accepted from the caller: a new item is
    physically in hand and nothing about it is under review, so `Available` is the only
    honest default — and `needs_review` must be `False`, or every addition would land
    unrentable in Phase 2 (ADR-0003).

    The id is asserted to be *new*, not merely present. The seed's ids run to 12 with
    one re-keyed row, so an implementation that lets SQLite pick an autoincrement value
    or reuses `max(id)` without adding to it would collide with a real item and
    overwrite it.
    """
    before = statuses_by_id(admin_client)

    response = admin_client.post(HARDWARE_PATH, json=NEW_ITEM)

    assert response.status_code in CREATED, (
        f"an admin must be able to add hardware; POST {HARDWARE_PATH} returned "
        f"{response.status_code}: {response.text}"
    )

    created = response.json()
    assert created["id"] not in before, (
        f"the new item must get an unused id; {created['id']} already belonged to "
        f"another item (ids in use: {sorted(before)})"
    )
    assert created["status"] == "Available", (
        f"a newly added item is in hand and not under review, so it must be Available; "
        f"got {created['status']!r}"
    )
    assert created["needs_review"] is False, (
        "a newly added item must not be flagged, or every addition arrives unrentable "
        "under ADR-0003"
    )

    after = statuses_by_id(admin_client)
    assert after.get(created["id"]) == "Available", (
        "the item must be readable back from the inventory — the response body is what "
        "the handler claims, the inventory is what it did"
    )
    assert set(before) < set(after), (
        f"adding must not disturb the existing inventory; before {sorted(before)}, "
        f"after {sorted(after)}"
    )


def test_non_admin_cannot_add_hardware(
    user_client: TestClient, anonymous_client: TestClient, admin_client: TestClient
) -> None:
    """A `user` session cannot add inventory, and the refusal writes nothing.

    Both halves again: the status code, and that the inventory is unchanged
    afterwards. A handler that inserts and then answers 403 passes a status-only test
    while having already grown the inventory.
    """
    before = statuses_by_id(admin_client)

    refused = user_client.post(HARDWARE_PATH, json=NEW_ITEM)
    assert refused.status_code == 403, (
        "a `user`-role session must be refused with 403 when adding hardware; got "
        f"{refused.status_code}: {refused.text}"
    )

    anonymous = anonymous_client.post(HARDWARE_PATH, json=NEW_ITEM)
    assert anonymous.status_code in (401, 403), (
        f"a caller with no session must be refused; got {anonymous.status_code}"
    )

    assert statuses_by_id(admin_client) == before, (
        "neither refusal may leave an item behind; the inventory changed from "
        f"{sorted(before)} to {sorted(statuses_by_id(admin_client))}"
    )


def test_added_hardware_requires_a_name(admin_client: TestClient) -> None:
    """A nameless item is refused, because the dashboard has nothing to show for it.

    `name` is the only field the seed never allowed to be absent — brand and purchase
    date are both nullable in real rows (seed id 10 has neither), so they stay optional
    here. An item with no name is a row a human cannot identify, which is exactly the
    defect record 10 exists to demonstrate.
    """
    response = admin_client.post(HARDWARE_PATH, json={"brand": "Framework"})

    assert response.status_code in (400, 422), (
        f"an item with no name must be refused; got {response.status_code}: "
        f"{response.text}"
    )
