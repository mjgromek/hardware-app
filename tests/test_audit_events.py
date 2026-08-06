"""Phase 2 Slice B — the record of an admin doing what an ordinary user could not.

ADR-0010 builds **one** table for two verbs, `force_return` and `clear_review_flag`,
with a closed `action` enum and a mandatory `reason`. The line it draws is the one
these three tests police from both sides: an admin override is recorded, and ordinary
product use is not.

That second half is easy to get wrong in the generous direction. Logging every rent and
return "for completeness" costs nothing to write and quietly destroys the table's
meaning — an audit trail where every row is routine is one nobody reads, and the Dell
XPS's eventual "cleared by admin, no reason given" is buried in nine hundred rentals.
The `rentals` row is already the record of a rental; this table is for the override.

The rows are read straight out of SQLite. Slice A and B ship no endpoint over
`audit_events` and none is planned, so there is no boundary to drive; see
`tests/conftest.py` on why that is raw SQL rather than an import of `app.rentals`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    ADMIN_EMAIL,
    audit_rows,
    clear_review_path,
    force_return_path,
    missing_columns,
    rent_path,
    rental_rows,
    return_path,
)

ACCEPTED = (200, 201, 204)

#: Seed id 1: `Available`, unflagged, nobody's.
FREE_ITEM = 1

#: Seed id 6, flagged at import for a 2027 purchase date.
FLAGGED_ITEM = 6

#: The columns ADR-0010 fixes.
AUDIT_COLUMNS = (
    "id",
    "actor_account_id",
    "actor_email",
    "action",
    "item_id",
    "rental_id",
    "reason",
    "created_at",
)

RECALL_REASON = "Reported battery swelling; recalled for service on 2026-08-06"
CLEAR_REASON = "Bench-tested by IT; purchase date was a data-entry error"


def test_force_return_writes_an_audit_event(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """Taking a laptop off an employee leaves a row saying who did it and why.

    `rental_id` is the assertion that makes this table worth having. An event that
    records only the item says an admin recalled *something* about that laptop at some
    point; one that names the rental ties the override to the specific person who was
    holding it, which is the question an incident actually asks. Nothing else in the
    schema recovers that link — the rental is closed by then, and a second recall of
    the same item later would be indistinguishable.

    The reason is compared verbatim rather than by substring. ADR-0010 accepts that a
    mandatory reason can be typed as "ok"; what it cannot survive is the reason being
    truncated, templated over, or replaced with the action name on the way in.
    """
    rented = user_client.post(rent_path(FREE_ITEM))
    recalled = admin_client.post(
        force_return_path(FREE_ITEM), json={"reason": RECALL_REASON}
    )

    events = audit_rows(app)
    assert len(events) == 1, (
        "a force-return writes exactly one audit event (ADR-0010) — none means the "
        "override is unrecorded, more than one means the table is being written from "
        f"two places. Got {len(events)}: {events}. The rent answered "
        f"{rented.status_code} and the recall answered {recalled.status_code}: "
        f"{recalled.text}"
    )

    event = events[0]
    absent = missing_columns(event, *AUDIT_COLUMNS)
    assert not absent, (
        f"the audit_events row is missing {absent} — ADR-0010 fixes the schema as "
        f"{list(AUDIT_COLUMNS)}; got {sorted(event)}"
    )

    assert event["action"] == "force_return", (
        "`action` is a closed enum and this row is a force-return; got "
        f"{event['action']!r}"
    )
    assert event["actor_email"] == ADMIN_EMAIL, (
        "the actor is the admin who sent the request, snapshotted like the renter is "
        f"(ADR-0007), so deleting the admin cannot erase who recalled it; got "
        f"{event['actor_email']!r}"
    )
    assert event["actor_account_id"] is not None, (
        "and their account id is recorded alongside the snapshot"
    )
    assert event["item_id"] == FREE_ITEM, (
        f"the event names the item; got {event['item_id']!r}"
    )
    assert event["reason"] == RECALL_REASON, (
        "the reason is stored verbatim — it is the only part of the row a human "
        f"wrote; got {event['reason']!r}"
    )
    assert event["created_at"], (
        "an audit event with no timestamp cannot be placed against the incident it is "
        f"being read about; got {event['created_at']!r}"
    )

    rows = rental_rows(app, FREE_ITEM)
    assert len(rows) == 1, f"setup: one rental was closed; got {rows}"
    assert event["rental_id"] == rows[0]["id"], (
        "the event points at the rental it ended, which is the only thing that ties "
        "the override to the employee who was holding the item — by the time anyone "
        f"reads this the rental is closed. Got rental_id={event['rental_id']!r} "
        f"against rental id {rows[0]['id']!r}"
    )


def test_force_return_itself_writes_the_event_not_its_caller(
    app, user_client: TestClient
) -> None:
    """The transition records the reason it demands; the route is not its keeper.

    `rentals.force_return` takes a mandatory `reason` (ADR-0010) and, until this test,
    ignored it — the audit write lived in the HTTP route. That passes every route test
    and still defeats the table: the *next* caller of the transition (the mvp-reviewer
    named Phase 3's auditor as the likely one) closes a rental and leaves no record,
    which is exactly the "audit trail becoming fiction" the function's own docstring
    warns about. An override the domain layer can perform silently is not audited, it
    is merely usually narrated.

    So this calls the transition directly, no route in sight, and asks the table.
    `test_force_return_writes_an_audit_event` holds the other side of the line: the
    route path still writes exactly one row, so moving the write down cannot leave it
    duplicated.
    """
    from app import rentals
    from app.accounts import verify_credentials
    from app.storage import new_session

    from tests.conftest import ADMIN_PASSWORD

    rented = user_client.post(rent_path(FREE_ITEM))
    assert rented.status_code in ACCEPTED, (
        f"setup: the item must be rented before it can be recalled; got "
        f"{rented.status_code}: {rented.text}"
    )

    with new_session(app.state.engine) as session:
        admin = verify_credentials(session, ADMIN_EMAIL, ADMIN_PASSWORD)
        assert admin is not None, "setup: the bootstrap admin must be retrievable"
        rental = rentals.force_return(session, FREE_ITEM, admin, RECALL_REASON)
        session.commit()

    events = audit_rows(app, action="force_return")
    assert len(events) == 1, (
        "`rentals.force_return` must write the audit event itself — a direct caller "
        "that closes a rental and records nothing is the override going unrecorded "
        f"(ADR-0010). Got {len(events)} events: {events}"
    )
    event = events[0]
    assert event["reason"] == RECALL_REASON, (
        "the reason the transition demanded is the reason it must store, verbatim; "
        f"got {event['reason']!r}"
    )
    assert event["rental_id"] == rental.id, (
        "the event points at the rental the transition closed; got "
        f"rental_id={event['rental_id']!r} against rental id {rental.id!r}"
    )
    assert event["actor_email"] == ADMIN_EMAIL, (
        f"the actor is the admin who recalled it; got {event['actor_email']!r}"
    )


def test_clearing_the_review_flag_writes_an_audit_event(
    app, admin_client: TestClient
) -> None:
    """Releasing a flagged machine is recorded as a claim somebody made.

    ADR-0003 makes this the condition of having a clear-flag mechanism at all:
    clearing is the assertion "somebody inspected this equipment and it is fit to
    issue", and a cleared flag that leaves no record of who cleared it and why turns
    the quarantine trail Phase 0 built into decoration at the one moment it matters.
    Ingestion already writes a reason for every divergence; the release must too.

    `rental_id` is `NULL` here, and asserting that is not pedantry — one table for two
    verbs (ADR-0010) means the nullable columns are how the two rows differ, and an
    implementation that reuses the force-return writer would attach whichever rental
    happened to be lying around.
    """
    cleared = admin_client.post(
        clear_review_path(FLAGGED_ITEM), json={"reason": CLEAR_REASON}
    )

    events = audit_rows(app)
    assert len(events) == 1, (
        f"clearing a review flag writes exactly one audit event; got {len(events)}: "
        f"{events}. The clear answered {cleared.status_code}: {cleared.text}"
    )

    event = events[0]
    absent = missing_columns(event, *AUDIT_COLUMNS)
    assert not absent, f"the audit_events row is missing {absent}; got {sorted(event)}"

    assert event["action"] == "clear_review_flag", (
        "the two verbs must be distinguishable in the table, or a reader cannot tell "
        "a recall from a release and the closed enum buys nothing; got "
        f"{event['action']!r}"
    )
    assert event["item_id"] == FLAGGED_ITEM, (
        f"the event names the item that was released; got {event['item_id']!r}"
    )
    assert event["actor_email"] == ADMIN_EMAIL, (
        f"the actor is the admin who cleared it; got {event['actor_email']!r}"
    )
    assert event["reason"] == CLEAR_REASON, (
        f"the reason is stored verbatim; got {event['reason']!r}"
    )
    assert event["rental_id"] is None, (
        "clearing a flag ends no rental, so the column stays NULL; got "
        f"{event['rental_id']!r}"
    )
    assert event["created_at"], f"the event is timestamped; got {event['created_at']!r}"


def test_ordinary_rent_and_return_write_no_audit_event(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """A user borrowing a laptop is the product working, not an override.

    ADR-0010 is explicit that ordinary rent and return write nothing here: the
    `rentals` row is their record, and this table is for an admin doing what an
    ordinary user could not. Logging both is the generous mistake — it costs nothing
    to write and dilutes the table until the two rows that matter are unfindable.

    The control at the end is what stops this test passing against an
    `audit_events` table that is never written to at all, which would be a much worse
    bug wearing the same green tick. It is also, until rent and return exist, the only
    thing holding this test red — "these verbs wrote nothing" is trivially true of
    verbs that did not run, and the control is what says so out loud.
    """
    cycles = [
        (
            user_client.post(rent_path(FREE_ITEM)).status_code,
            user_client.post(return_path(FREE_ITEM)).status_code,
        )
        for _ in range(2)
    ]
    assert all(
        code in ACCEPTED for cycle in cycles for code in cycle
    ), (
        "two rent→return cycles must complete before this test can say what they did "
        f"not record; the cycles answered (rent, return) = {cycles}"
    )

    assert not audit_rows(app), (
        "two complete rent→return cycles must leave the audit table empty — they are "
        "recorded as rentals, and an audit trail where routine use outnumbers "
        f"overrides is one nobody reads. Got {audit_rows(app)}"
    )

    held = user_client.post(rent_path(FREE_ITEM))
    recalled = admin_client.post(
        force_return_path(FREE_ITEM), json={"reason": RECALL_REASON}
    )

    assert len(audit_rows(app, action="force_return")) == 1, (
        "control failed: an admin override must write its event. Got "
        f"{audit_rows(app)}. With nothing ever written to audit_events, the assertion "
        f"above passes against a table that does not work at all. The rent answered "
        f"{held.status_code} and the recall answered {recalled.status_code}: "
        f"{recalled.text}"
    )
