"""Phase 2 — putting the seed's defects back, on purpose and repeatably.

Verifying v2 against the live instance consumed the very state the project demonstrates:
item 7's rental was recalled, and ids 6 and 10 had their flags cleared. Those three rows
are not decoration — `docs/DATA_AUDIT.md` is written about them, ADR-0002 keeps the
semantic contradictions for Phase 3's auditor to find, and a reviewer opening the live URL
should see the mess the brief supplied.

So the reset is a product feature of a demo instance, not a script somebody runs once.

**It is an HTTP route because nothing else can reach the data.** Railway exposes no exec
and no SSH — the reason `seed_if_empty` exists at all — so a CLI reset would be a
documented command nobody can run against the deployment it is documented for.

**It clears the blocker rather than bypassing it.** ADR-0011 has `persist` refuse while
rentals exist, and that refusal is correct and stays. The reset deletes the rentals and
the audit events *first*, and only then reseeds, so it goes through the guard rather than
around it. A reset implemented with a `force=True` flag on `persist` would have removed
the protection for every other caller.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import rentals
from app.storage import create_engine_for, load_items, load_quarantine, new_session
from tests.conftest import HARDWARE_PATH, items_by_id, rent_path

RESET_PATH = "/api/admin/reset-demo"

#: Typed in full, so the request cannot be issued by accident or by a curl someone
#: half-remembers. It is destructive by design and reads that way.
CONFIRMATION = "reset the demo data"

FLAGGED_IDS = {6, 10}
HELD_ITEM = 7
SEED_RENTER_EMAIL = "j.doe@booksy.com"


def test_reset_restores_the_seed_fingerprints(
    app, admin_client: TestClient, user_client: TestClient, database_path: Path
) -> None:
    """After a demo has been played with, one call puts every fingerprint back.

    The setup deliberately destroys all three: it recalls the seed rental, clears both
    flags, and rents an unrelated item so there is live rental state in the way — which
    is exactly what ADR-0011's refusal exists to protect and what the reset must clear
    before it can reseed.

    The assertions are the four things `docs/DATA_AUDIT.md` claims, checked as a set
    rather than a count: an audit document that only matches on totals passes against
    the wrong eleven rows.
    """
    admin_client.post(
        f"{HARDWARE_PATH}/{HELD_ITEM}/force-return", json={"reason": "demo walkthrough"}
    )
    for item_id in FLAGGED_IDS:
        admin_client.post(
            f"{HARDWARE_PATH}/{item_id}/clear-review", json={"reason": "demo walkthrough"}
        )
    assert user_client.post(rent_path(1)).status_code in (200, 201), "setup"

    spoiled = items_by_id(admin_client)
    assert not any(item["needs_review"] for item in spoiled.values()), (
        "setup: the demo must actually be spoiled, or this test proves nothing"
    )

    response = admin_client.post(RESET_PATH, json={"confirm": CONFIRMATION})
    assert response.status_code in (200, 204), (
        f"an admin must be able to restore the demo; POST {RESET_PATH} returned "
        f"{response.status_code}: {response.text}"
    )

    restored = items_by_id(admin_client)
    assert len(restored) == 11, f"the seed imports 11 items; got {len(restored)}"
    assert {i for i, item in restored.items() if item["needs_review"]} == FLAGGED_IDS, (
        "ids 6 and 10 are flagged at import and are what the review queue demonstrates; "
        f"got {sorted(i for i, x in restored.items() if x['needs_review'])}"
    )
    assert restored[HELD_ITEM]["status"] == "In Use", (
        f"seed id {HELD_ITEM} arrives held; got {restored[HELD_ITEM]['status']!r}"
    )
    assert restored[HELD_ITEM]["assigned_to"] == SEED_RENTER_EMAIL, (
        f"and held by {SEED_RENTER_EMAIL}; got {restored[HELD_ITEM]['assigned_to']!r}"
    )
    assert restored[12]["source_id"] == 4, (
        "the duplicate id 4 is re-keyed to 12 and keeps its source id — the fingerprint "
        f"`docs/DATA_AUDIT.md` predicted before the code existed; got {restored.get(12)}"
    )
    assert restored[9]["brand"] == "Appel", (
        "the 'Appel' typo survives, because ingestion is structural only (ADR-0002) and "
        f"the typo is Phase 3's to find; got {restored[9]['brand']!r}"
    )

    engine = create_engine_for(f"sqlite:///{database_path}")
    with new_session(engine) as session:
        assert len(load_quarantine(session)) == 3, (
            "three quarantine records, for ids 2, 6 and 10 — the reseed has to rebuild "
            "the audit trail, not just the inventory"
        )
        seed_rental = rentals.active_rental(session, HELD_ITEM)
        assert seed_rental is not None and seed_rental.account_id is None, (
            "the seed rental comes back accountless (ADR-0007), so item 7 is held and "
            f"recallable exactly as it is on a fresh install; got {seed_rental}"
        )
        assert rentals.active_rental(session, 1) is None, (
            "and the rental taken during the demo is gone — the reset clears rentals "
            "before reseeding, which is how it gets past ADR-0011's refusal"
        )
        assert len(load_items(session)) == 11


def test_reset_requires_the_confirmation_phrase(
    app, admin_client: TestClient
) -> None:
    """A missing or wrong phrase changes nothing.

    The route destroys rental history on a live instance. A bare `POST` that fires on
    the first request is one mistyped URL away from wiping the thing ADR-0011 was
    written to protect.
    """
    assert admin_client.post(rent_path(1)).status_code in (200, 201), "setup"

    for body in ({}, {"confirm": ""}, {"confirm": "yes"}, {"confirm": "RESET THE DEMO DATA"}):
        response = admin_client.post(RESET_PATH, json=body)
        assert response.status_code in (400, 422), (
            f"{body!r} must not be enough to reset the demo; got {response.status_code}"
        )

    assert items_by_id(admin_client)[1]["status"] == "In Use", (
        "the refused reset must leave the rental it would have destroyed"
    )


def test_non_admin_cannot_reset_the_demo(
    user_client: TestClient, anonymous_client: TestClient, admin_client: TestClient
) -> None:
    """The published demo account cannot wipe the demo.

    `demo@booksy.com` is a `user` precisely so a published credential cannot destroy
    anything (`/security-review`), and this is the most destructive route in the app.
    """
    assert user_client.post(rent_path(1)).status_code in (200, 201), "setup"

    assert user_client.post(RESET_PATH, json={"confirm": CONFIRMATION}).status_code == 403
    assert anonymous_client.post(
        RESET_PATH, json={"confirm": CONFIRMATION}
    ).status_code in (401, 403)

    assert items_by_id(admin_client)[1]["status"] == "In Use", (
        "neither refusal may have reseeded anything"
    )
