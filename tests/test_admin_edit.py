"""Phase 4 — an admin can correct what a row says about a device.

Edit is wireframe-driven, not brief-required: the brief scopes admin actions to
add/delete/toggle-Repair, and the wireframe's pencil is the reason this exists (see
`docs/WIREFRAME_JUSTIFICATION.md`). It rides the existing `PATCH /api/hardware/{id}`
— one mutation route, where the status guards already live — with partial-update
semantics: only the fields sent change, and the status guards (a held item cannot go
to Repair, ADR-0009) are untouched by edits that never mention status.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import HARDWARE_PATH, items_by_id

ACCEPTED = (200, 204)

#: Seed id 1: Available, unflagged, fully populated — edits to it are visible
#: against known values.
EDITABLE_ITEM = 1


def _patch(client: TestClient, item_id: int, **fields):
    return client.patch(f"{HARDWARE_PATH}/{item_id}", json=fields)


def test_admin_can_edit_every_field(admin_client: TestClient) -> None:
    """Name, brand, purchase date, serial and category all change and all persist.

    Asserted off the listing rather than the response body — the row a colleague
    reads tomorrow is the claim, not the echo of the request.
    """
    response = _patch(
        admin_client,
        EDITABLE_ITEM,
        name="iPhone 13 Pro Max (engraved)",
        brand="Apple Inc.",
        purchase_date="2021-12-01",
        serial_number="F17G8XYZPLJM",
        category="Mobile",
    )
    assert response.status_code in ACCEPTED, (
        f"an admin must be able to edit an item; got {response.status_code}: "
        f"{response.text}"
    )

    listed = items_by_id(admin_client)[EDITABLE_ITEM]
    assert listed["name"] == "iPhone 13 Pro Max (engraved)"
    assert listed["brand"] == "Apple Inc."
    assert listed["purchase_date"] == "2021-12-01"
    assert listed["serial_number"] == "F17G8XYZPLJM"
    assert listed["category"] == "Mobile"


def test_edit_changes_only_the_fields_sent(admin_client: TestClient) -> None:
    """A partial edit is partial: everything unmentioned keeps its value.

    The failure this exists to catch is the handler that treats an absent field as
    null and quietly blanks a brand every time somebody fixes a typo in the name.
    """
    before = items_by_id(admin_client)[EDITABLE_ITEM]

    response = _patch(admin_client, EDITABLE_ITEM, name="Renamed only")
    assert response.status_code in ACCEPTED, response.text

    after = items_by_id(admin_client)[EDITABLE_ITEM]
    assert after["name"] == "Renamed only"
    untouched = {
        key: (before[key], after[key])
        for key in ("brand", "purchase_date", "status", "needs_review", "serial_number", "category")
        if before[key] != after[key]
    }
    assert not untouched, (
        f"fields the edit never mentioned must keep their values; changed: {untouched}"
    )


def test_non_admin_cannot_edit(user_client: TestClient, admin_client: TestClient) -> None:
    """A `user` gets 403 and the row is untouched — editing is inventory curation."""
    before = items_by_id(admin_client)[EDITABLE_ITEM]

    refused = _patch(user_client, EDITABLE_ITEM, name="mine now")
    assert refused.status_code == 403, (
        f"an employee must be refused the edit; got {refused.status_code}: "
        f"{refused.text}"
    )
    assert items_by_id(admin_client)[EDITABLE_ITEM]["name"] == before["name"], (
        "and the refused edit must not have changed the row"
    )


def test_edit_refuses_an_off_enum_category(admin_client: TestClient) -> None:
    """The closed set holds on the edit path too — `422`, row untouched."""
    before = items_by_id(admin_client)[EDITABLE_ITEM]

    refused = _patch(admin_client, EDITABLE_ITEM, category="Desktop")
    assert refused.status_code == 422, (
        f"an off-enum category is refused on edit exactly as on add; got "
        f"{refused.status_code}: {refused.text}"
    )
    assert items_by_id(admin_client)[EDITABLE_ITEM]["category"] == before["category"]


def test_edit_refuses_a_blank_name(admin_client: TestClient) -> None:
    """A name of spaces is refused — the same rule the add form enforces.

    An item whose name renders as nothing is indistinguishable from a rendering bug,
    and is exactly the unidentifiable record seed id 10 exists to demonstrate.
    """
    refused = _patch(admin_client, EDITABLE_ITEM, name="   ")
    assert refused.status_code == 422, (
        f"a blank name must be refused; got {refused.status_code}: {refused.text}"
    )


def test_edit_of_a_missing_item_is_404(admin_client: TestClient) -> None:
    refused = _patch(admin_client, 4040, name="ghost")
    assert refused.status_code == 404, (
        f"editing an item that does not exist is a 404; got {refused.status_code}: "
        f"{refused.text}"
    )


def test_empty_edit_is_refused(admin_client: TestClient) -> None:
    """A PATCH that changes nothing is a `422`, not a silent success.

    An empty body reaching the database as a no-op UPDATE would report success for
    a request that expressed no intent — the 'sorting doesn't work sometimes' class
    of bug, one route over.
    """
    refused = admin_client.patch(f"{HARDWARE_PATH}/{EDITABLE_ITEM}", json={})
    assert refused.status_code == 422, (
        f"an edit naming no fields must be refused; got {refused.status_code}: "
        f"{refused.text}"
    )
