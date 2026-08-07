"""Phase 4 — a release note must describe a change the same action made.

The defect this closes is a documentation defect that the code enforced. `clear-review`
demanded a note beginning `fixed:` (ADR-0017) but gave the admin no way to fix anything
from that action — so resolving seed id 6 meant writing "fixed: corrected the purchase
date" while the purchase date stayed 2027-10-10. The note certified work the system had
not done, and the audit trail recorded the certification as though it had.

ADR-0010 exists so that "somebody inspected this and it is fit to issue" can be
interrogated later. A note asserting a correction that never happened is worse than no
note: it is a false record with an actor's name on it.

So the release carries the edit. One action, one transaction, one `audit_events` row
holding both the change and the reason for it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import HARDWARE_PATH, audit_rows, items_by_id

#: Seed id 6 — the future purchase date. The item the note is supposed to be about.
FUTURE_DATED_ITEM = 6
CORRECTED_DATE = "2021-10-10"
RELEASE = "fixed: corrected the purchase date from 2027 to 2021"


def _clear_path(item_id: int) -> str:
    return f"{HARDWARE_PATH}/{item_id}/clear-review"


def test_release_applies_the_edit_it_describes(app, admin_client: TestClient) -> None:
    """The note says the date was corrected, so the date is corrected.

    Asserted through the inventory rather than the response body: the claim is that the
    change *landed*, and a handler can return a corrected item while writing nothing.
    """
    before = items_by_id(admin_client)[FUTURE_DATED_ITEM]
    assert before["needs_review"] is True, "setup: seed id 6 imports flagged"
    assert before["purchase_date"] == "2027-10-10", (
        f"setup: the future date is the thing being fixed; got {before['purchase_date']!r}"
    )

    response = admin_client.post(
        _clear_path(FUTURE_DATED_ITEM),
        json={"reason": RELEASE, "purchase_date": CORRECTED_DATE},
    )

    assert response.status_code in (200, 204), (
        f"an admin must be able to fix the record and release it in one action; got "
        f"{response.status_code}: {response.text}"
    )

    after = items_by_id(admin_client)[FUTURE_DATED_ITEM]
    assert after["purchase_date"] == CORRECTED_DATE, (
        "the release note says the date was corrected, so the date must be corrected — "
        "a note certifying a change the action did not make is a false record with an "
        f"actor's name on it; got {after['purchase_date']!r}"
    )
    assert after["needs_review"] is False, (
        "and the item is released in the same action, not left flagged"
    )
    assert after["review_reason"] is None, (
        "the reason for the flag goes with the flag"
    )
    assert after["name"] == before["name"], (
        "fields the admin did not send are untouched — a partial edit that blanks the "
        f"name while fixing a date is how a typo fix loses data; got {after['name']!r}"
    )


def test_release_records_the_change_and_the_reason_in_one_event(
    app, admin_client: TestClient
) -> None:
    """One audit row, carrying the note — not one for the edit and one for the release.

    Two rows would let the pair come apart: a reader finding the release would have to
    join it to an edit by timestamp to learn whether the certified change happened.
    """
    before = len(audit_rows(app))

    admin_client.post(
        _clear_path(FUTURE_DATED_ITEM),
        json={"reason": RELEASE, "purchase_date": CORRECTED_DATE},
    )

    rows = audit_rows(app)
    assert len(rows) == before + 1, (
        f"one action writes one event; the trail went from {before} to {len(rows)}"
    )
    written = rows[-1]
    assert RELEASE in (written["reason"] or ""), (
        f"the event carries the release note verbatim; got {written['reason']!r}"
    )
    assert written["item_id"] == FUTURE_DATED_ITEM


def test_a_rejected_edit_leaves_the_item_flagged(app, admin_client: TestClient) -> None:
    """If the edit will not apply, nothing applies — the flag stays.

    This is the assertion that makes it one transaction rather than two statements in a
    row. A handler that clears the flag and *then* fails on the category would release
    an item whose record is still wrong, and the release note would describe a fix that
    was rejected — the same false certification, arrived at from the other side.
    """
    before = items_by_id(admin_client)[FUTURE_DATED_ITEM]
    audit_before = len(audit_rows(app))

    response = admin_client.post(
        _clear_path(FUTURE_DATED_ITEM),
        json={"reason": RELEASE, "category": "Submarine"},
    )

    assert response.status_code in (400, 422), (
        f"an off-enum category must be refused; got {response.status_code}: "
        f"{response.text[:160]}"
    )

    after = items_by_id(admin_client)[FUTURE_DATED_ITEM]
    assert after["needs_review"] is True, (
        "the refused edit must leave the item flagged — releasing it anyway would "
        "publish a release note for a correction the server rejected"
    )
    assert after["purchase_date"] == before["purchase_date"], "and unchanged"
    assert len(audit_rows(app)) == audit_before, (
        "and must write no audit event, because nothing happened"
    )


def test_a_release_with_no_edit_still_works(app, admin_client: TestClient) -> None:
    """Not every finding needs a field changed.

    Seed id 10's problem is that nobody knows what it is; an admin who has physically
    identified it has fixed something the record cannot express as a field edit. The
    edit is optional — what is mandatory is the note.
    """
    response = admin_client.post(
        _clear_path(FUTURE_DATED_ITEM), json={"reason": "fixed: inspected, record is correct"}
    )

    assert response.status_code in (200, 204), (
        f"a release with no field changes must still be allowed; got "
        f"{response.status_code}: {response.text}"
    )
    assert items_by_id(admin_client)[FUTURE_DATED_ITEM]["needs_review"] is False
