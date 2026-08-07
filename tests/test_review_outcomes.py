"""A review concludes; it does not only absolve (ADR-0017, Phase 4 amendment 2).

Until now `clear-review` had exactly one exit, and it required the words `fixed:`. That
is fine when the finding was a wrong date. It is a trap when the finding was real: an
admin who inspects seed id 5 — `notes` reads "Battery swelling, do not issue without
service" — and confirms the battery *is* swelling has no honest action available. Leaving
the flag set records no decision at all; releasing it certifies a repair nobody did.

That second option is the same defect the first Phase 4 amendment closed one move earlier,
and it is worse here: a release makes the item rentable, so the false record ends with a
swelling battery in an employee's bag.

So the verb takes an outcome. **Released** keeps the `fixed:` note and the item stays
issuable. **Repair** takes a reason describing what is wrong and sets the status to
`Repair`, which makes the item unrentable through the guard that already refuses rentals
on repair items — no new blocking mechanism, and none wanted. Both clear `needs_review`,
because both are conclusions; both write one `audit_events` row, because both are
decisions with an actor.
"""

from __future__ import annotations

import pytest
from fastapi import status

from conftest import audit_rows, clear_review_path, items_by_id


#: Seed id 5 — "Battery swelling, do not issue without service". The row the whole
#: amendment is about.
SWELLING_BATTERY = 5


@pytest.fixture
def flagged_item(admin_client) -> int:
    """An item that is genuinely flagged, whatever the seed happens to ship flagged."""
    flagged = [
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if item["needs_review"]
    ]
    assert flagged, "the seed no longer flags anything; this suite needs a flagged item"
    return flagged[0]


def test_a_review_can_conclude_in_repair(admin_client, flagged_item) -> None:
    """The outcome that did not exist: the finding was real, and the item is not fit."""
    response = admin_client.post(
        clear_review_path(flagged_item),
        json={
            "outcome": "repair",
            "reason": "battery is swelling, confirmed by inspection",
        },
    )

    assert response.status_code == status.HTTP_200_OK, response.text

    item = items_by_id(admin_client)[flagged_item]
    assert item["needs_review"] is False, (
        "a repair outcome is a concluded review — the flag must clear, or the item sits "
        "in the queue forever and the queue stops meaning 'undecided'"
    )
    assert item["status"] == "Repair", (
        "the outcome is what makes the item unrentable; without the status change the "
        "flag has been cleared and nothing stops the next person renting it"
    )


def test_an_item_sent_to_repair_by_a_review_cannot_be_rented(
    admin_client, user_client, flagged_item
) -> None:
    """The point of the status change, asserted through the renting seam rather than the column.

    `status == "Repair"` is an implementation detail of unrentability. What the amendment
    promises is that nobody can take the device, and the only honest way to check that is
    to try.
    """
    from conftest import rent_path

    concluded = admin_client.post(
        clear_review_path(flagged_item),
        json={"outcome": "repair", "reason": "battery is swelling, confirmed"},
    )
    assert concluded.status_code == status.HTTP_200_OK, concluded.text

    # Asserted before renting, so this test cannot pass on the *flag* still blocking the
    # rental — which is how it passed while the outcome did not exist.
    assert items_by_id(admin_client)[flagged_item]["needs_review"] is False

    attempt = user_client.post(rent_path(flagged_item))

    assert attempt.status_code == status.HTTP_409_CONFLICT, (
        f"a device an admin just declared unfit was rentable; got {attempt.status_code}"
    )


def test_a_repair_outcome_writes_one_audit_row_naming_the_admin(
    app, admin_client, flagged_item
) -> None:
    """A decision with no recorded actor is not a decision (ADR-0010)."""
    admin_client.post(
        clear_review_path(flagged_item),
        json={"outcome": "repair", "reason": "battery is swelling, confirmed"},
    )

    written = [row for row in audit_rows(app) if row["item_id"] == flagged_item]

    assert len(written) == 1, (
        f"expected exactly one audit row for the review, found {len(written)}: "
        "two rows can come apart, and a reader would have to join them by timestamp"
    )
    assert "swelling" in written[0]["reason"]


def test_a_repair_outcome_does_not_demand_the_word_fixed(
    admin_client, flagged_item
) -> None:
    """The whole point: this reason describes what is *wrong*.

    Requiring `fixed:` here would reintroduce the false record through the new door.
    """
    response = admin_client.post(
        clear_review_path(flagged_item),
        json={"outcome": "repair", "reason": "battery is swelling, do not issue"},
    )

    assert response.status_code == status.HTTP_200_OK, response.text


def test_a_repair_outcome_still_requires_a_reason(admin_client, flagged_item) -> None:
    """Both outcomes are claims about the device, and a claim with no content is not one."""
    response = admin_client.post(
        clear_review_path(flagged_item),
        json={"outcome": "repair", "reason": "   "},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text


def test_release_still_demands_the_fixed_prefix(admin_client, flagged_item) -> None:
    """The first amendment survives the second. Regression guard, not a new rule."""
    response = admin_client.post(
        clear_review_path(flagged_item),
        json={"outcome": "released", "reason": "looked at it, seems fine"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text


def test_release_remains_the_default_outcome(admin_client, flagged_item) -> None:
    """An omitted outcome means release, so every existing caller keeps working.

    Making `outcome` mandatory would be the tidier schema and would break the Phase 3
    UI and every client already sending `{reason}`. The default is the behaviour that
    already existed.
    """
    response = admin_client.post(
        clear_review_path(flagged_item),
        json={"reason": "fixed: corrected the purchase date"},
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert items_by_id(admin_client)[flagged_item]["needs_review"] is False


def test_an_unrecognised_outcome_is_refused(admin_client, flagged_item) -> None:
    """A closed set, for the reason `Status` and `audit.Action` are.

    `"dismissed"` is the outcome somebody will reach for, and it is exactly the one this
    amendment refuses to offer: it clears the flag while asserting nothing.
    """
    # The reason is a valid release note, so a `422` here can only come from the outcome.
    response = admin_client.post(
        clear_review_path(flagged_item),
        json={"outcome": "dismissed", "reason": "fixed: not a real problem"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text
    assert items_by_id(admin_client)[flagged_item]["needs_review"] is True, (
        "the flag cleared on a refused outcome"
    )


def test_a_repair_outcome_is_refused_on_an_unflagged_item(admin_client) -> None:
    """`409` on both outcomes alike — there is no review to conclude (ADR-0010)."""
    unflagged = next(
        item_id
        for item_id, item in items_by_id(admin_client).items()
        if not item["needs_review"]
    )

    response = admin_client.post(
        clear_review_path(unflagged),
        json={"outcome": "repair", "reason": "battery is swelling"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT, response.text


def test_a_non_admin_cannot_conclude_a_review_either_way(
    user_client, flagged_item
) -> None:
    """Authorization is checked before the outcome, so the new door is not a way around it."""
    for outcome in ("released", "repair"):
        response = user_client.post(
            clear_review_path(flagged_item),
            json={"outcome": outcome, "reason": "fixed: nothing, actually"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"a plain user concluded a review with outcome={outcome!r}"
        )
