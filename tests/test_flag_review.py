"""Phase 3 Slice C — the flag-review verb: a human acts on what the auditor found.

`POST /api/hardware/{id}/flag-review`, admin-only, mandatory reason (ADR-0017). Sets
`needs_review`, writes `review_reason` — human authors only, never the model
(ADR-0014) — and records an `audit_events` row, which is exactly the actor ADR-0010
reserved the table for. `409` on an already-flagged item, symmetric with
`clear-review`: idempotency would file a mandatory reason against a non-event.

This is the verb that makes the auditor a product rather than a report: without it, a
finding about the Dell XPS changes nothing, which is ADR-0003's "a flag that changes
nothing is decoration" one level up.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    ADMIN_EMAIL,
    HARDWARE_PATH,
    audit_rows,
    items_by_id,
    rent_path,
)

ACCEPTED = (200, 201, 204)

#: Seed id 5, the Dell XPS: `Available`, unflagged at import (ADR-0002 keeps ingestion
#: structural), and the item every grilling used as the case that must become
#: flaggable once a human has read the auditor's finding.
DELL_XPS = 5

FLAG_REASON = "Auditor finding confirmed by IT: battery swelling, do not issue."


def flag_path(item_id: int) -> str:
    return f"{HARDWARE_PATH}/{item_id}/flag-review"


def test_admin_can_flag_item_for_review(admin_client: TestClient) -> None:
    """Flagging sets the flag and records the admin's reason on the item.

    The reason lands in `review_reason` so the queue can explain the restriction —
    written by the human who decided, never by the model (ADR-0014).
    """
    response = admin_client.post(flag_path(DELL_XPS), json={"reason": FLAG_REASON})

    assert response.status_code in ACCEPTED, (
        f"an admin must be able to flag an item (ADR-0017); got "
        f"{response.status_code}: {response.text}"
    )
    item = items_by_id(admin_client)[DELL_XPS]
    assert item["needs_review"] is True, (
        f"the flag must actually be set; got {item}"
    )
    assert item["review_reason"] == FLAG_REASON, (
        "`review_reason` carries the admin's own words, so the queue can explain "
        f"the restriction; got {item['review_reason']!r}"
    )


def test_flagging_blocks_rental(
    admin_client: TestClient, user_client: TestClient
) -> None:
    """The loop closes end to end: flagged by a human, refused by the guard.

    ADR-0003 made `needs_review` a rentability guard; ADR-0017 is what finally lets a
    human put the Dell XPS behind it. If this test fails, the auditor can find the
    swelling battery and the product still hands the laptop out.
    """
    flagged = admin_client.post(flag_path(DELL_XPS), json={"reason": FLAG_REASON})
    assert flagged.status_code in ACCEPTED, (
        f"setup: the flag must be settable first; got {flagged.status_code}: "
        f"{flagged.text}"
    )

    refused = user_client.post(rent_path(DELL_XPS))
    assert refused.status_code == 409, (
        "a flagged item is unrentable through the same guard as Repair (ADR-0003). "
        f"Got {refused.status_code}: {refused.text}"
    )


def test_flag_review_requires_a_reason(admin_client: TestClient) -> None:
    """No reason, no flag — and a whitespace reason is no reason (ADR-0017)."""
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        response = admin_client.post(flag_path(DELL_XPS), json=body)
        assert response.status_code == 422, (
            f"a flag with body {body!r} must be refused as unprocessable — the "
            "mandatory reason is the whole point of recording the decision "
            f"(ADR-0010). Got {response.status_code}: {response.text}"
        )
    item = items_by_id(admin_client)[DELL_XPS]
    assert item["needs_review"] is False, (
        f"and none of the refused attempts may have set the flag; got {item}"
    )


def test_flag_review_writes_an_audit_event(admin_client: TestClient, app) -> None:
    """The decision is recorded with its actor — what ADR-0010 reserved the table for."""
    response = admin_client.post(flag_path(DELL_XPS), json={"reason": FLAG_REASON})
    assert response.status_code in ACCEPTED, response.text

    events = audit_rows(app, action="flag_review")
    assert len(events) == 1, (
        "flagging is an admin override and writes exactly one audit event "
        f"(ADR-0017); got {audit_rows(app)}"
    )
    event = events[0]
    assert event["actor_email"] == ADMIN_EMAIL, (
        f"the actor is the admin who decided; got {event['actor_email']!r}"
    )
    assert event["item_id"] == DELL_XPS, (
        f"the event names the item; got {event['item_id']!r}"
    )
    assert event["reason"] == FLAG_REASON, (
        f"the reason is stored verbatim; got {event['reason']!r}"
    )
    assert event["rental_id"] is None, (
        f"flagging ends no rental, so the column stays NULL; got {event['rental_id']!r}"
    )


def test_flag_review_409_when_already_flagged(admin_client: TestClient, app) -> None:
    """Re-flagging a flagged item is refused, symmetric with `clear-review`.

    Idempotency here would hide a UI bug *and* file a mandatory reason against a
    non-event (ADR-0010's reasoning, pointed the other way by ADR-0017).
    """
    first = admin_client.post(flag_path(DELL_XPS), json={"reason": FLAG_REASON})
    assert first.status_code in ACCEPTED, f"setup: {first.status_code}: {first.text}"

    second = admin_client.post(flag_path(DELL_XPS), json={"reason": "Still broken."})
    assert second.status_code == 409, (
        "an already-flagged item refuses a second flag (ADR-0017); got "
        f"{second.status_code}: {second.text}"
    )
    assert len(audit_rows(app, action="flag_review")) == 1, (
        "and the refused attempt must not have written a second event; got "
        f"{audit_rows(app)}"
    )


def test_non_admin_cannot_flag(
    user_client: TestClient, admin_client: TestClient, app
) -> None:
    """A `user` gets `403`, the flag stays down, and no event is attributed to them.

    Flagging makes an item unrentable for everyone — an authorization short of admin
    would let any employee take inventory out of circulation under their own name.
    """
    refused = user_client.post(flag_path(DELL_XPS), json={"reason": FLAG_REASON})

    assert refused.status_code == 403, (
        f"an employee must be refused the flag verb; got {refused.status_code}: "
        f"{refused.text}"
    )
    assert items_by_id(admin_client)[DELL_XPS]["needs_review"] is False, (
        "and the flag must not have been set by the refused request"
    )
    assert not audit_rows(app), (
        f"a refusal writes no audit event; got {audit_rows(app)}"
    )
