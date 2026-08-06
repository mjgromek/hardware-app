"""Phase 2 Slice B — who sees what on a hardware item (ADR-0012).

The line: **renter identity is visible to every signed-in user; `notes`, `history` and
`review_reason` are admin-only.** Both halves are tested, because each without the
other describes a different product. Hide the renter and the point of `In Use` on an
internal tool disappears — nobody can find out who has the headphones, the conversation
moves to Slack, and the rental log stops matching reality. Show the notes and every
employee reads maintenance prose written for an auditor, which is the open field-level
`/security-review` finding the README has been carrying since Phase 1.

**This is the change that is invisible to every existing test.** `GET /api/hardware`
returned whole items to everybody through Phase 0 and Phase 1, and nothing asserted who
may see which field — a serialiser that forgets one is caught by nothing else in the
suite. ADR-0012 says so in its own consequences.

The leak is asserted twice over: structurally, that the restricted keys are absent or
null in a user's payload, and textually, that the sensitive strings themselves do not
appear anywhere in the response body. The second catches the case the first cannot — a
serialiser that renames the field, folds the note into a summary, or leaves it on a
nested object.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.conftest import (
    HARDWARE_PATH,
    OTHER_USER_EMAIL,
    items_by_id,
    rent_path,
)

ACCEPTED = (200, 201, 204)

#: Admin- and auditor-facing free text (ADR-0012).
RESTRICTED_FIELDS = ("notes", "history", "review_reason")

#: The seed's own prose, quoted from `data/seed.json`. If any of this reaches a
#: `user`, the field-level finding is still open whatever the payload keys say.
SENSITIVE_TEXT = (
    "Battery swelling",          # seed id 5, the Dell XPS's notes
    "liquid damage",             # seed id 11, the MacBook Air's history
    "is in the future",          # seed id 6's review_reason, written by ingestion
    "not a recognised status",   # seed id 10's review_reason
)

#: Fields an employee needs to use the dashboard at all.
OPERATIONAL_FIELDS = ("id", "name", "brand", "purchase_date", "status", "needs_review")

#: Seed id 7: `In Use` from import, held by an address with no account.
HELD_ITEM = 7
SEED_RENTER_EMAIL = "j.doe@booksy.com"

#: Seed id 1: `Available`, unflagged.
FREE_ITEM = 1


def _payload_text(item: dict) -> str:
    """Everything one serialised item says, flattened for a substring search."""
    return json.dumps(item, default=str).lower()


def test_user_does_not_receive_notes_or_history(
    user_client: TestClient, admin_client: TestClient
) -> None:
    """A `user`'s inventory carries no maintenance prose, and no fewer rows.

    The admin's view is read first and asserted non-empty for each restricted field.
    That is not decoration: without it, an endpoint that returned `notes: null` to
    everybody — or that dropped the columns from the query entirely — would satisfy
    every assertion below while having broken the admin panel and the Phase 3 auditor,
    who both read exactly these fields.

    The row-count assertion is the other control. Restricting *fields* must not
    restrict *items*; a serialiser that filters flagged rows out of a user's response
    instead of filtering their text hides inventory from the people who use it, and
    ADR-0012 is explicit that the flag itself stays visible so the employee can see
    why they cannot rent something.
    """
    admin_view = items_by_id(admin_client)
    for field in RESTRICTED_FIELDS:
        assert any(item.get(field) for item in admin_view.values()), (
            f"setup: an admin must receive a non-empty {field!r} on at least one seed "
            "item, or this test cannot distinguish 'restricted from users' from "
            "'never serialised for anyone'"
        )

    response = user_client.get(HARDWARE_PATH)
    assert response.status_code == 200, (
        f"a signed-in user must still get the inventory; got {response.status_code}: "
        f"{response.text}"
    )
    user_view = {item["id"]: item for item in response.json()}

    leaked = {
        (item_id, field): item[field]
        for item_id, item in user_view.items()
        for field in RESTRICTED_FIELDS
        if item.get(field) is not None
    }
    assert not leaked, (
        "`notes`, `history` and `review_reason` are admin-only (ADR-0012) — they are "
        "maintenance prose written for an auditor, and Phase 3 writes findings into "
        f"the same columns. A user received: {leaked}"
    )

    body = response.text.lower()
    for phrase in SENSITIVE_TEXT:
        assert phrase.lower() not in body, (
            f"the seed's own text {phrase!r} reached a `user`'s response body. The "
            "key-level check above passes if the serialiser renames the field, folds "
            "it into a summary, or nests it — this is the assertion that does not"
        )

    assert set(user_view) == set(admin_view), (
        "restricting fields must not restrict rows: a user sees the same inventory, "
        f"with less of it filled in. Admin saw {sorted(admin_view)}, user saw "
        f"{sorted(user_view)}"
    )
    for field in OPERATIONAL_FIELDS:
        assert all(field in item for item in user_view.values()), (
            f"a user still needs {field!r} to use the dashboard — `needs_review` in "
            "particular stays visible so the flag can explain a refusal, which is "
            "ADR-0012's stated compensation for hiding the reason"
        )


def test_renter_identity_is_visible_to_every_signed_in_user(
    user_client: TestClient, other_user_client: TestClient, admin_client: TestClient
) -> None:
    """Any employee can see who is holding an item — the seed's, and a live one.

    ADR-0012 keeps this visible deliberately: the point of `In Use` on an internal tool
    is knowing who to ask for the headphones, and hiding it moves that conversation
    somewhere the tool cannot see.

    The live rental is the half that is not seed residue. `assigned_to` arrived from
    the seed as a bare string, and an implementation can serve `In Use` for a freshly
    rented item without ever telling anybody who took it — the status changes, the
    rental row is written, and the dashboard shows an anonymous "In Use" that nobody
    can act on. ADR-0012 is explicit that `assigned_to` "stops being seed residue and
    becomes live data about which colleague is holding which laptop".

    Asserted as "the holder's address appears somewhere in the item's payload" rather
    than against a named column, because which field carries it is a serialisation
    choice and this is a test about what an employee can find out.
    """
    seed_item = items_by_id(user_client)[HELD_ITEM]
    assert seed_item["status"] == "In Use", (
        f"setup: seed item {HELD_ITEM} must be In Use; got {seed_item['status']!r}"
    )
    assert SEED_RENTER_EMAIL.lower() in _payload_text(seed_item), (
        f"a signed-in employee must be able to see that {SEED_RENTER_EMAIL} is "
        "holding the headphones — hiding the renter moves 'who has this?' to Slack "
        f"(ADR-0012); got {seed_item}"
    )

    rented = other_user_client.post(rent_path(FREE_ITEM))

    as_a_colleague = items_by_id(user_client)[FREE_ITEM]
    assert as_a_colleague["status"] == "In Use", (
        f"item {FREE_ITEM} must read In Use to a colleague once somebody has taken "
        f"it; the rent answered {rented.status_code}: {rented.text}, and the item "
        f"reads {as_a_colleague['status']!r}"
    )
    assert OTHER_USER_EMAIL.lower() in _payload_text(as_a_colleague), (
        f"a live rental must name its holder too: {OTHER_USER_EMAIL} just took item "
        f"{FREE_ITEM} and a colleague's dashboard shows an anonymous 'In Use'. The "
        "renter's identity is live data now, not seed residue (ADR-0012); got "
        f"{as_a_colleague}"
    )
    assert OTHER_USER_EMAIL.lower() in _payload_text(items_by_id(admin_client)[FREE_ITEM]), (
        "and an admin sees the holder as well — the admin payload is a superset of "
        "the user's, never a different set"
    )
