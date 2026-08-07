"""Phase 4 — the note describing a fault must be editable by whoever fixes it.

ADR-0017 was just amended so a release note describes a change the same action performed.
`notes` is the field that most often *is* the fault: seed id 5 reads "Battery swelling, do
not issue without service", and an admin releasing it with "fixed: replaced the battery"
while that text still stands has published a correction the record contradicts. Same false
record ADR-0017 closed, one field over — and this one is worse, because the stale note is
what the Phase 3 auditor reads and what the next admin sees when deciding whether to issue
the device.

`notes` stays admin-only (ADR-0012). Editable and readable by admins, absent for everyone
else — the field being writable does not widen who may see it, and these tests pin both
halves so a serialiser change cannot quietly trade one for the other.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import HARDWARE_PATH, audit_rows, items_by_id

#: Seed id 5, the Dell XPS — `Available`, with notes recording a swelling battery. The
#: row ADR-0002 deliberately left for a human to judge.
FAULTY_ITEM = 5

#: Seed id 6 — flagged at import, so it is the one a release can be tested against.
FLAGGED_ITEM = 6

REPAIRED = "Battery replaced 2026-08-07, bench-tested, safe to issue."


def test_admin_can_edit_notes(admin_client: TestClient) -> None:
    """The field is writable through the ordinary edit route, and it lands.

    Read back through the inventory rather than trusting the response: the claim is that
    the text changed for everybody who reads it next, not that a handler echoed it.
    """
    before = items_by_id(admin_client)[FAULTY_ITEM]
    assert before["notes"], (
        f"setup: seed id {FAULTY_ITEM} carries the swelling-battery note; got "
        f"{before['notes']!r}"
    )

    response = admin_client.patch(f"{HARDWARE_PATH}/{FAULTY_ITEM}", json={"notes": REPAIRED})

    assert response.status_code in (200, 204), (
        f"an admin must be able to correct the note that describes a fault; got "
        f"{response.status_code}: {response.text}"
    )

    after = items_by_id(admin_client)[FAULTY_ITEM]
    assert after["notes"] == REPAIRED, (
        "the stale note is what the Phase 3 auditor reads and what the next admin sees "
        f"when deciding whether to issue the device; got {after['notes']!r}"
    )
    assert after["name"] == before["name"], (
        "and only the field that was sent changed"
    )


def test_a_user_can_neither_read_nor_write_notes(
    user_client: TestClient, admin_client: TestClient
) -> None:
    """Making the field writable must not make it visible.

    Two assertions because they fail independently: a serialiser that starts returning
    `notes` to everyone, and a route that lets a `user` write one. ADR-0012 restricts the
    field on both axes, and widening one while tightening the other is the mistake this
    catches.
    """
    admin_view = items_by_id(admin_client)[FAULTY_ITEM]
    assert admin_view["notes"], "setup: an admin sees the note"

    served = items_by_id(user_client)[FAULTY_ITEM]
    assert served.get("notes") is None, (
        "`notes` is admin-only maintenance prose (ADR-0012) — a `user` receives null, "
        f"whether or not the field is editable; got {served.get('notes')!r}"
    )

    refused = user_client.patch(f"{HARDWARE_PATH}/{FAULTY_ITEM}", json={"notes": "harmless"})
    assert refused.status_code == 403, (
        f"a `user` must be refused the edit route with 403; got {refused.status_code}"
    )
    assert items_by_id(admin_client)[FAULTY_ITEM]["notes"] == admin_view["notes"], (
        "and the refused write must not have landed"
    )


def test_a_release_can_correct_the_note_it_certifies(
    app, admin_client: TestClient
) -> None:
    """The whole point: one action fixes the text and clears the flag, in one event.

    A release that updates `notes` and a release that updates `purchase_date` must behave
    identically — ADR-0017's amendment is about the *class* of problem, not one column.
    One `audit_events` row carrying the note, or a reader has to join two rows by
    timestamp to learn whether the certified fix happened.
    """
    before = len(audit_rows(app))
    release = "fixed: replaced the swelling battery, bench-tested"

    response = admin_client.post(
        f"{HARDWARE_PATH}/{FLAGGED_ITEM}/clear-review",
        json={"reason": release, "notes": REPAIRED},
    )

    assert response.status_code in (200, 204), (
        f"a release must be able to carry a notes correction; got "
        f"{response.status_code}: {response.text}"
    )

    item = items_by_id(admin_client)[FLAGGED_ITEM]
    assert item["notes"] == REPAIRED, (
        f"the note the release certifies must be the note stored; got {item['notes']!r}"
    )
    assert item["needs_review"] is False, "and the item is released in the same action"

    rows = audit_rows(app)
    assert len(rows) == before + 1, (
        f"one action, one event; the trail went from {before} to {len(rows)}"
    )
    assert release in (rows[-1]["reason"] or "")
