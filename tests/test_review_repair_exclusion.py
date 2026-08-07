"""Review and Repair are mutually exclusive, in both directions (ADR-0003, amended).

One direction already held: concluding a review in Repair clears the flag, because a
review that reaches a conclusion is over (ADR-0017, second Phase 4 amendment).

The other did not. `POST /flag-review` accepted any unflagged item, including one already
sitting in `Repair`, which produced a row that was simultaneously "an admin has taken this
out of service" and "somebody needs to decide about this". Those are different questions
with different owners, and an item asserting both tells a reader neither: the review queue
gains an entry nobody can conclude — releasing it would return a broken device to service
— and the repair queue gains an item whose status is under debate.

It also made the display precedence ambiguous. `In Repair > In Review` resolves the pill,
but a rule that exists to pick between two states a row should never be in at once is a
patch over the hole, not a fix for it.

The exclusion is by construction now: the flag verb refuses, `409`, through the guard
layer that already refuses every other impossible transition.
"""

from __future__ import annotations

import pytest
from fastapi import status

from conftest import audit_rows, items_by_id


def flag_path(item_id: int) -> str:
    return f"/api/hardware/{item_id}/flag-review"


@pytest.fixture
def repair_item(admin_client) -> int:
    """An item an admin has taken out of service."""
    target = next(
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["status"] == "Available" and not item["needs_review"]
    )
    moved = admin_client.patch(f"/api/hardware/{target}", json={"status": "Repair"})
    assert moved.status_code == status.HTTP_200_OK, moved.text
    return target


def test_an_item_in_repair_cannot_be_flagged_for_review(admin_client, repair_item) -> None:
    """The missing half of the exclusion.

    `409` rather than `422`: nothing about the request is malformed. The item is in a
    state that makes the action meaningless, which is what the guard layer answers with
    everywhere else in this project.
    """
    response = admin_client.post(
        flag_path(repair_item), json={"reason": "somebody should look at this"}
    )

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert items_by_id(admin_client)[repair_item]["needs_review"] is False, (
        "the flag was refused and set anyway"
    )


def test_the_refusal_explains_itself(admin_client, repair_item) -> None:
    """A guard that refuses without saying why is a wall (CONTEXT.md).

    The admin's next move is to take the item out of Repair or to leave it there, and the
    message has to be enough to choose between them.
    """
    response = admin_client.post(
        flag_path(repair_item), json={"reason": "somebody should look at this"}
    )

    detail = response.json()["detail"].lower()
    assert "repair" in detail, response.json()["detail"]
    assert any(word in detail for word in ("already", "out of service", "cannot")), (
        f"the reason does not say what is wrong: {response.json()['detail']!r}"
    )


def test_a_refused_flag_writes_no_audit_row(app, admin_client, repair_item) -> None:
    """A refusal is a non-event. Filing a mandatory reason against one is the same
    mistake ADR-0010 refused when it made `clear-review` `409` on an unflagged item."""
    before = len(audit_rows(app))

    admin_client.post(flag_path(repair_item), json={"reason": "somebody should look"})

    assert len(audit_rows(app)) == before


def test_concluding_a_review_in_repair_still_clears_the_flag(admin_client) -> None:
    """The direction that already held, pinned so the new guard cannot break it.

    This is the one path that legitimately moves an item *into* Repair while a flag
    exists, and it must keep working — the guard refuses `flag-review`, not the status
    change that concludes a review.
    """
    flagged = next(
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["needs_review"]
    )

    concluded = admin_client.post(
        f"/api/hardware/{flagged}/clear-review",
        json={"outcome": "repair", "reason": "battery is swelling, confirmed"},
    )

    assert concluded.status_code == status.HTTP_200_OK, concluded.text
    item = items_by_id(admin_client)[flagged]
    assert item["status"] == "Repair"
    assert item["needs_review"] is False, (
        "the two states are both true at once — the exclusion this guard exists for"
    )


def test_no_seeded_item_is_both_flagged_and_in_repair(admin_client) -> None:
    """The invariant, asserted over the whole catalogue rather than one path.

    A guard on one route is only as good as the set of routes that can reach the state.
    If this ever fails, some *other* path has learned to produce the combination.
    """
    both = [
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["needs_review"] and item["status"] == "Repair"
    ]

    assert both == [], f"items {both} are flagged for review while in Repair"


def test_a_flagged_item_cannot_be_patched_into_repair(admin_client) -> None:
    """The other way into the forbidden pair, and the one that actually produced it.

    Found by looking at the dashboard after the `flag-review` guard shipped: a row was
    showing `In Repair` *and* the amber flag marker. Guarding one route is only as good
    as the set of routes that reach the state, and admin edit reaches it — `PATCH` with
    `status: "Repair"` on a flagged item wrote the combination with nothing to stop it.

    Refused rather than silently resolved. Clearing the flag here would conclude a review
    with no reason and no audit row, which is what `clear-review` exists to prevent — and
    the verb that *does* conclude a review in Repair is one call away.
    """
    flagged = next(
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["needs_review"] and item["status"] != "Repair"
    )

    response = admin_client.patch(
        f"/api/hardware/{flagged}", json={"status": "Repair"}
    )

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    detail = response.json()["detail"].lower()
    assert "review" in detail, response.json()["detail"]

    item = items_by_id(admin_client)[flagged]
    assert not (item["needs_review"] and item["status"] == "Repair"), (
        "admin edit produced the combination the exclusion forbids"
    )


def test_a_flagged_item_can_still_be_patched_to_other_statuses(admin_client) -> None:
    """The guard is Repair-shaped here too — it must not freeze a flagged item's status.

    Correcting an ingestion mistake on a flagged row (id 10's status was `Unknown`) is
    ordinary admin work and has nothing to do with the review's conclusion.
    """
    flagged = next(
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["needs_review"] and item["status"] != "Repair"
    )

    response = admin_client.patch(
        f"/api/hardware/{flagged}", json={"status": "Available"}
    )

    assert response.status_code == status.HTTP_200_OK, response.text


def test_an_item_can_still_be_flagged_while_rented(admin_client, user_client) -> None:
    """The exclusion is Repair-shaped, not a general "no flags on busy items".

    `In Use` and `needs_review` coexist legitimately: somebody holding a device can be
    told it is under review, and the flag is what stops the *next* rental. Widening the
    guard to every non-Available status would break that.
    """
    available = next(
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["status"] == "Available" and not item["needs_review"]
    )
    user_client.post(f"/api/hardware/{available}/rent")

    response = admin_client.post(
        flag_path(available), json={"reason": "purchase record looks wrong"}
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    item = items_by_id(admin_client)[available]
    assert item["needs_review"] is True
    assert item["status"] == "In Use"
