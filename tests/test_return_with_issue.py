"""A returner may flag what they handled (ADR-0020).

Until now the only way into `needs_review` was an admin acting on an auditor finding
(ADR-0017), and the only way out was an admin concluding the review. That leaves the one
person who actually held the device with nowhere to put what they noticed: the loop seed
id 11's history implies — *"Returned by user with a note"* — had no verb.

The asymmetry with ADR-0014 is deliberate and is the whole argument of ADR-0020: the
auditor may not set the flag because it reasons over stored text, while a returner
reports what they observed in their hands. Direct observation licenses direct action;
inference does not. It is not "humans outrank models" — an admin acting on a *finding*
still goes through the admin verb.

The reported note becomes the `review_reason` verbatim, because paraphrasing the only
first-hand account into a house style is how the detail that mattered gets lost.
"""

from __future__ import annotations

import pytest
from fastapi import status

from conftest import audit_rows, items_by_id, rent_path, return_path


@pytest.fixture
def rented_item(admin_client, user_client) -> int:
    """An item the plain user is holding, ready to be handed back."""
    available = next(
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["status"] == "Available" and not item["needs_review"]
    )
    taken = user_client.post(rent_path(available))
    assert taken.status_code == status.HTTP_200_OK, taken.text
    return available


def test_a_plain_return_leaves_the_item_unflagged(user_client, admin_client, rented_item) -> None:
    """"All good" is still the ordinary return, and must stay a one-click path.

    The new question cannot become a tax on the common case: nearly every return is
    fine, and a flow that makes the honest majority fill in a field teaches people to
    type nothing into it.
    """
    response = user_client.post(return_path(rented_item))

    assert response.status_code == status.HTTP_200_OK, response.text

    item = items_by_id(admin_client)[rented_item]
    assert item["needs_review"] is False
    assert item["status"] == "Available"


def test_returning_with_an_issue_flags_the_item(user_client, admin_client, rented_item) -> None:
    """The verb ADR-0020 adds: the return happens *and* the flag goes up."""
    response = user_client.post(
        return_path(rented_item),
        json={"issue": "screen flickers when the lid moves"},
    )

    assert response.status_code == status.HTTP_200_OK, response.text

    item = items_by_id(admin_client)[rented_item]
    assert item["status"] != "In Use", (
        "the return must still happen — a report is not a refusal to hand the item back"
    )
    assert item["needs_review"] is True, (
        "the reported fault did not raise the flag, so the next person can rent it"
    )


def test_the_reported_note_becomes_the_review_reason_verbatim(
    user_client, admin_client, rented_item
) -> None:
    """The returner's words, not a summary of them (the ADR-0017 principle, one actor over)."""
    note = "screen flickers when the lid moves past about 90 degrees"

    user_client.post(return_path(rented_item), json={"issue": note})

    assert items_by_id(admin_client)[rented_item]["review_reason"] == note


def test_a_reported_item_cannot_be_rented_by_the_next_person(
    user_client, other_user_client, admin_client, rented_item
) -> None:
    """The point of flagging, asserted through the renting seam rather than the column.

    `needs_review` blocks rental (ADR-0003), so this needs no new mechanism — but that
    is a claim about behaviour, and the honest way to check it is to try to rent.
    """
    user_client.post(return_path(rented_item), json={"issue": "screen flickers"})

    attempt = other_user_client.post(rent_path(rented_item))

    assert attempt.status_code == status.HTTP_409_CONFLICT, (
        f"a device just reported faulty was rentable; got {attempt.status_code}"
    )


def test_a_reported_return_records_the_returner_as_the_actor(
    app, user_client, rented_item
) -> None:
    """Whose observation this was is the first thing a reviewing admin needs.

    A flag attributed to nobody, or to the admin who later reads it, cannot be followed
    up — the reviewer's next move is to ask the person who held it.
    """
    user_client.post(return_path(rented_item), json={"issue": "screen flickers"})

    flags = [
        row
        for row in audit_rows(app)
        if row["item_id"] == rented_item and row["action"] == "report_on_return"
    ]

    assert len(flags) == 1, (
        f"expected one report_on_return row, found {len(flags)}; a flag raised by a "
        "user must be attributable to that user"
    )
    assert "flickers" in flags[0]["reason"]


def test_an_empty_issue_is_refused_rather_than_flagging_with_nothing(
    user_client, admin_client, rented_item
) -> None:
    """Whitespace is not an observation.

    A flag whose reason is `"   "` is worse than no flag: it blocks the item and tells
    the admin resolving it nothing at all. Same floor as every other mandatory reason.
    """
    response = user_client.post(return_path(rented_item), json={"issue": "   "})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text
    assert items_by_id(admin_client)[rented_item]["needs_review"] is False


def test_reporting_on_someone_elses_rental_is_still_refused(
    other_user_client, admin_client, rented_item
) -> None:
    """ADR-0009 is untouched: the new field is not a way to close a rental you do not hold.

    Direct observation is the licence, and somebody who never had the device has none.
    """
    response = other_user_client.post(
        return_path(rented_item), json={"issue": "I heard it rattles"}
    )

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert items_by_id(admin_client)[rented_item]["needs_review"] is False, (
        "a user who does not hold the item flagged it anyway"
    )


def test_reporting_on_an_already_flagged_item_keeps_the_return_working(
    admin_client, user_client, rented_item
) -> None:
    """The `409` that guards the admin verb must not strand a returner holding hardware.

    `flag-review` refuses an already-flagged item, because filing a mandatory reason
    against a non-event hides a UI bug (ADR-0017). Here the priority is inverted: the
    return is the physical fact, and refusing it would leave somebody holding a device
    the system still believes they have. The report is folded into the existing flag.
    """
    admin_client.post(
        f"/api/hardware/{rented_item}/flag-review",
        json={"reason": "flagged by an admin while it was out"},
    )

    response = user_client.post(
        return_path(rented_item), json={"issue": "and the screen flickers"}
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    item = items_by_id(admin_client)[rented_item]
    assert item["status"] != "In Use", "the return was refused over the existing flag"
    assert item["needs_review"] is True
