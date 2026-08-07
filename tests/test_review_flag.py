"""Phase 2 Slice B — clearing `needs_review`, the thing nothing could do until now.

ADR-0003 shipped a rentability guard with no release valve and said so in its own
consequences: "nothing clears `needs_review`, so a flagged item is unrentable
indefinitely, and today that is two of eleven items in the seed." Phase 1 wrote that
into the README as a documented shortcut. This is the file that closes it.

**`test_cleared_item_becomes_rentable` is the one that matters.** A flag that clears
but still blocks rental is the decoration ADR-0003 exists to prevent, arriving in a new
place — and it is entirely plausible: `needs_review` is read by the guard *and*
rendered as a dashboard column, so an implementation that clears the column an admin
can see, while the guard consults something else, looks completely finished.

`409` and not `404` for an unflagged item (ADR-0010): the item exists, the request is
permitted, and there is simply nothing to clear. Idempotency was rejected deliberately
— a silent success would hide a UI bug *and* write a mandatory reason against a
non-event.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    audit_rows,
    clear_review_path,
    items_by_id,
    rent_path,
    rental_rows,
    statuses_by_id,
)

ACCEPTED = (200, 201, 204)

#: Seed id 6, the Logitech mouse: flagged for a 2027 purchase date, `Available`.
FLAGGED_ITEM = 6

#: Seed id 10, "Unknown Device": flagged for an off-enum status, also `Available`.
OTHER_FLAGGED_ITEM = 10

#: Seed id 1: `Available` and never flagged.
UNFLAGGED_ITEM = 1

NO_SUCH_ITEM = 9999

REASON = "fixed: purchase date corrected in the asset register on 2026-08-06"


def _flag_of(admin_client: TestClient, item_id: int) -> bool:
    return items_by_id(admin_client)[item_id]["needs_review"]


def test_admin_can_clear_needs_review(app, admin_client: TestClient) -> None:
    """An admin clears the flag on one item, and only on that item.

    The `review_reason` has to go with it. Leaving the reason behind on a cleared item
    means the dashboard shows an explanation for a flag that is not there, and the
    Phase 3 auditor reads the same column — ADR-0012 makes `review_reason` admin-only
    precisely because it is auditor-facing prose, and stale prose is worse than none.

    The blast-radius assertion is the discriminating one: "item 6 is no longer flagged"
    is also true of a handler that cleared the flag on every row, and of one that
    ignored the id in the path. Both look correct on a queue screen showing one line,
    and both silently release the other contradictory machine.
    """
    before = items_by_id(admin_client)
    assert before[FLAGGED_ITEM]["needs_review"] is True, (
        f"setup: seed item {FLAGGED_ITEM} must import flagged; got "
        f"{before[FLAGGED_ITEM]!r}"
    )
    assert before[FLAGGED_ITEM]["review_reason"], (
        f"setup: a flagged item carries the reason it was flagged, and this test "
        f"asserts the reason is cleared with the flag; got "
        f"{before[FLAGGED_ITEM]['review_reason']!r}"
    )
    assert before[OTHER_FLAGGED_ITEM]["needs_review"] is True, (
        f"setup: seed item {OTHER_FLAGGED_ITEM} must also import flagged, or the "
        "blast-radius assertion below has nothing to compare against"
    )

    response = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": REASON})

    assert response.status_code in ACCEPTED, (
        f"an admin with a reason must be able to clear the flag; POST "
        f"{clear_review_path(FLAGGED_ITEM)} returned {response.status_code}: "
        f"{response.text}"
    )

    after = items_by_id(admin_client)
    assert after[FLAGGED_ITEM]["needs_review"] is False, (
        f"item {FLAGGED_ITEM} must read as unflagged afterwards; got "
        f"{after[FLAGGED_ITEM]['needs_review']!r}"
    )
    assert after[FLAGGED_ITEM]["review_reason"] is None, (
        "the reason for the flag goes with the flag — a cleared item still showing "
        "'purchase date 2027-10-10 is in the future' explains a restriction that no "
        f"longer applies; got {after[FLAGGED_ITEM]['review_reason']!r}"
    )
    assert after[OTHER_FLAGGED_ITEM]["needs_review"] is True, (
        f"clearing item {FLAGGED_ITEM} must not have cleared item "
        f"{OTHER_FLAGGED_ITEM} — a handler that ignores the id in the path releases "
        "every flagged machine at once, and looks right on a queue showing one row"
    )
    assert after[FLAGGED_ITEM]["status"] == before[FLAGGED_ITEM]["status"], (
        "clearing the flag is not a status change. The two are orthogonal (ADR-0010), "
        f"which is why the flag has its own column and not a fourth chip; got "
        f"{after[FLAGGED_ITEM]['status']!r}"
    )


def test_cleared_item_becomes_rentable(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """Clearing the flag actually releases the item — the whole point of Slice B.

    Three acts, in this order deliberately. Refused *before*, so the guard is known to
    have been firing and the success afterwards is not a route that never blocked
    anything. Cleared. Rented, and the rent must be a real one — status `In Use` and a
    rental row — because a `200` from an endpoint that wrote nothing would satisfy a
    status-code-only assertion.

    An implementation that clears the column the dashboard renders while the guard
    reads its own copy passes `test_admin_can_clear_needs_review` completely and fails
    here, which is exactly the split ADR-0003's "a flag that changes nothing is
    decoration" was written about.
    """
    refused = user_client.post(rent_path(FLAGGED_ITEM))
    assert refused.status_code == 409, (
        f"item {FLAGGED_ITEM} must be unrentable *before* the flag is cleared, or the "
        "success below is a route that never blocked anything rather than a flag that "
        f"was released; got {refused.status_code}: {refused.text}"
    )

    cleared = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": REASON})
    rented = user_client.post(rent_path(FLAGGED_ITEM))

    assert rented.status_code in ACCEPTED, (
        f"a cleared item must be rentable. The clear answered {cleared.status_code} "
        f"and renting item {FLAGGED_ITEM} afterwards returned {rented.status_code}: "
        f"{rented.text}. A flag that clears in the dashboard but still blocks the "
        "rental is the decoration ADR-0003 exists to prevent, in a new place"
    )
    assert statuses_by_id(admin_client)[FLAGGED_ITEM] == "In Use", (
        "and the rent must be a real one, not a 200 over an UPDATE that matched "
        f"nothing; got {statuses_by_id(admin_client)[FLAGGED_ITEM]!r}"
    )
    assert len(rental_rows(app, FLAGGED_ITEM)) == 1, (
        f"one rental row for the newly released item; got "
        f"{rental_rows(app, FLAGGED_ITEM)}"
    )


def test_clearing_an_unflagged_item_is_refused(
    app, admin_client: TestClient
) -> None:
    """Nothing to clear is a `409`, whether it was never flagged or already cleared.

    Both routes to "not flagged", because they are reached by different callers: the
    first is an admin clicking the wrong row, the second is a double-click or a stale
    queue screen. ADR-0010 rejects idempotency here for both — a silent success hides
    the UI bug that sent the second request, and writes a mandatory reason against an
    event that did not happen.

    The audit table is asserted empty afterwards, which is the consequence half of the
    refusal. A handler that writes the event and then answers `409` has already put
    "somebody inspected this equipment and it is fit to issue" into the record for an
    inspection nobody did.
    """
    assert _flag_of(admin_client, UNFLAGGED_ITEM) is False, (
        f"setup: seed item {UNFLAGGED_ITEM} must import unflagged"
    )

    never = admin_client.post(clear_review_path(UNFLAGGED_ITEM), json={"reason": REASON})
    assert never.status_code == 409, (
        "clearing a flag that is not set must be refused with 409 — the item exists "
        f"and the admin is permitted, there is just nothing to clear (ADR-0010); got "
        f"{never.status_code}: {never.text}"
    )
    assert not audit_rows(app), (
        "a refused clear must write no audit event; the trail now records an "
        f"inspection that never happened: {audit_rows(app)}"
    )

    first = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": REASON})
    assert first.status_code in ACCEPTED, (
        f"setup: the first clear must succeed; got {first.status_code}: {first.text}"
    )
    events_after_first = len(audit_rows(app))

    again = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": REASON})
    assert again.status_code == 409, (
        "clearing an already-cleared item is refused for the same reason — a "
        "double-click must not be indistinguishable from a second inspection; got "
        f"{again.status_code}: {again.text}"
    )
    assert len(audit_rows(app)) == events_after_first, (
        "and it must not add a second audit event; the trail went from "
        f"{events_after_first} to {len(audit_rows(app))} rows"
    )

    missing = admin_client.post(clear_review_path(NO_SUCH_ITEM), json={"reason": REASON})
    assert missing.status_code == 404, (
        "an id that is not in the inventory is a 404, not a 409 — nothing conflicts, "
        f"the item is not there; got {missing.status_code}: {missing.text}"
    )


def test_clearing_requires_a_reason(app, admin_client: TestClient) -> None:
    """No reason, no clearance — and spaces are not a reason.

    Clearing is the assertion "somebody inspected this equipment and it is fit to
    issue", which is exactly the claim a later incident interrogates. ADR-0003 makes
    the record of *who and why* the condition of having the mechanism at all, and
    ADR-0010 accepts that the reason can be typed as "ok" — the field cannot force
    thought, only a record that somebody was asked. The empty string is the value that
    means nobody was asked.

    Whitespace is checked because `min_length=1` accepts `"   "`; the identical hole
    was found in Phase 1's add-hardware form by `test_whitespace_only_name_is_refused`.
    """
    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "\n\t"}):
        response = admin_client.post(clear_review_path(FLAGGED_ITEM), json=body)
        assert response.status_code in (400, 422), (
            f"a clear-review with body {body!r} states no reason and must be refused "
            f"as malformed; got {response.status_code}: {response.text}"
        )

    assert _flag_of(admin_client, FLAGGED_ITEM) is True, (
        f"no reasonless request may have cleared the flag on item {FLAGGED_ITEM}"
    )
    assert not audit_rows(app), (
        f"and none may have written an audit event; got {audit_rows(app)}"
    )

    allowed = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": REASON})
    assert allowed.status_code in ACCEPTED, (
        "control failed: a clear *with* a reason must work. Got "
        f"{allowed.status_code}: {allowed.text}"
    )


def test_non_admin_cannot_clear_needs_review(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """An employee cannot release the machine that was flagged as unsafe to issue.

    This is the escalation the guard exists to stop: `needs_review` blocks the rental,
    and the person most motivated to clear it is the person who just tried to rent it.
    If they can, ADR-0003's guard is advisory.

    `403` and not `409`: they are refused for who they are, and the item's state has
    nothing to do with it. The control is an admin doing the same thing successfully,
    without which "clear-review refuses everybody" passes.
    """
    response = user_client.post(
        clear_review_path(FLAGGED_ITEM), json={"reason": "I need a mouse today"}
    )

    assert response.status_code == 403, (
        "a `user`-role session must be refused with 403 when clearing a review flag; "
        f"got {response.status_code}: {response.text}"
    )
    assert _flag_of(admin_client, FLAGGED_ITEM) is True, (
        "the refused clear must leave the flag set — a handler that clears and then "
        "answers 403 has already released the item"
    )
    assert not audit_rows(app), (
        f"and it must write no audit event attributed to a non-admin; got "
        f"{audit_rows(app)}"
    )

    still_blocked = user_client.post(rent_path(FLAGGED_ITEM))
    assert still_blocked.status_code == 409, (
        "and the item must still be unrentable to them; got "
        f"{still_blocked.status_code}: {still_blocked.text}"
    )

    allowed = admin_client.post(clear_review_path(FLAGGED_ITEM), json={"reason": REASON})
    assert allowed.status_code in ACCEPTED, (
        "control failed: an admin must be able to clear the flag. Got "
        f"{allowed.status_code}: {allowed.text}"
    )
