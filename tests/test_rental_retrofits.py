"""Phase 2 Slice A — three shipped paths that destroy or corrupt rental data.

None of these routes is new. `PATCH /api/hardware/{id}`, `DELETE /api/hardware/{id}`
and `persist` all shipped in Phase 0 or Phase 1 and all three were correct until the
moment rentals existed. That is why they are in one file: they are the *retrofit*, and
a reviewer asking "what did Phase 2 change about work that was already green" should
find the answer in one place rather than inferred from three.

- **`PATCH` → `Repair` on a held item** (ADR-0009). `CONTEXT.md` lists "a rented item
  in `Repair`" as an impossible state, and Phase 1 shipped the route that reaches it.
- **`DELETE` on a held item** (ADR-0011). Leaves a rental pointing at nothing.
- **`persist` while rentals exist** (ADR-0011). The README publishes the reseed command
  as a live operation, and `persist` truncates `hardware`.

**Phase 1's two tests do not need changing, and that is checked rather than assumed.**
`test_admin_can_toggle_repair_status` and `test_non_admin_cannot_delete_hardware` both
target seed id 1, which imports `Available` with no rental, so neither new guard can
fire against them. ADR-0009 says as much in its consequences — "needs a companion, not
a change". The companions are here.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.storage import create_engine_for, create_schema, load_items, new_session, persist
from scripts.seed import ingest
from tests.conftest import (
    DELETED,
    HARDWARE_PATH,
    UPDATED,
    USER_EMAIL,
    force_return_path,
    rent_path,
    rental_rows,
    return_path,
    statuses_by_id,
)

ACCEPTED = (200, 201, 204)

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed.json"
TODAY = date(2026, 8, 6)

#: Seed id 7, held from import by an address with no account (ADR-0007).
HELD_ITEM = 7
SEED_RENTER_EMAIL = "j.doe@booksy.com"

#: Seed id 1 and 4: `Available`, unflagged, nobody's.
FREE_ITEM = 1
CONTROL_ITEM = 4


def _seed_report():
    return ingest(json.loads(SEED_PATH.read_text(encoding="utf-8")), today=TODAY)


# --------------------------------------------------------------------------
# Repair against a held item (ADR-0009)
# --------------------------------------------------------------------------


def test_cannot_set_repair_on_a_held_item(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """An admin must recall a laptop before sending it for service, not instead of it.

    The refusal has to **name the holder**, because the reason is the instruction: an
    admin who is told "no" and not "Sara has it" has to go and look the rental up
    before they can act, and the next thing they will do is flip the status anyway.

    Both kinds of holder are checked. Seed id 7 is held by an address with no account,
    which is the case an implementation that resolves the holder through the users
    table gets wrong — it finds nobody and concludes the item is free.

    The final act is ADR-0009's whole argument in three requests: force-return, then
    `Repair`. A swelling battery on a held laptop costs an admin two deliberate
    actions instead of one silent one, and buys a rental log with no rental in it that
    ended without a record of who ended it.
    """
    before = statuses_by_id(admin_client)
    assert before[HELD_ITEM] == "In Use", (
        f"setup: seed item {HELD_ITEM} must import In Use; got {before[HELD_ITEM]!r}"
    )

    seed_held = admin_client.patch(
        f"{HARDWARE_PATH}/{HELD_ITEM}", json={"status": "Repair"}
    )
    assert seed_held.status_code == 409, (
        "moving a held item to Repair is the impossible state CONTEXT.md names, and "
        f"must be refused with 409; got {seed_held.status_code}: {seed_held.text}"
    )
    assert SEED_RENTER_EMAIL in seed_held.text, (
        "the reason must name the holder so the admin knows who to recall it from "
        f"(ADR-0009) — and {SEED_RENTER_EMAIL} has no account, which is the holder an "
        f"implementation reading the users table cannot find; got {seed_held.text!r}"
    )
    assert statuses_by_id(admin_client)[HELD_ITEM] == "In Use", (
        "the refused PATCH must leave the status alone"
    )

    rented = user_client.post(rent_path(FREE_ITEM))
    assert rented.status_code in ACCEPTED, (
        f"setup: the employee must be holding item {FREE_ITEM}; got "
        f"{rented.status_code}: {rented.text}"
    )

    freshly_held = admin_client.patch(
        f"{HARDWARE_PATH}/{FREE_ITEM}", json={"status": "Repair"}
    )
    assert freshly_held.status_code == 409, (
        "an item held by a live rental is refused the same way as one held since "
        f"import; got {freshly_held.status_code}: {freshly_held.text}"
    )
    assert USER_EMAIL in freshly_held.text, (
        f"the reason must name {USER_EMAIL} as the holder; got {freshly_held.text!r}"
    )
    assert len(rental_rows(app, FREE_ITEM)) == 1, (
        "the refused PATCH must not have touched the rental"
    )

    control = admin_client.patch(
        f"{HARDWARE_PATH}/{CONTROL_ITEM}", json={"status": "Repair"}
    )
    assert control.status_code in UPDATED, (
        "control failed: an admin must still be able to send an *unheld* item for "
        f"service — the guard protects held items, not the Repair toggle. Got "
        f"{control.status_code}: {control.text}"
    )

    recalled = admin_client.post(
        force_return_path(FREE_ITEM), json={"reason": "Battery swelling reported"}
    )
    assert recalled.status_code in ACCEPTED, (
        f"setup: the admin's recall must work; got {recalled.status_code}: "
        f"{recalled.text}"
    )
    after_recall = admin_client.patch(
        f"{HARDWARE_PATH}/{FREE_ITEM}", json={"status": "Repair"}
    )
    assert after_recall.status_code in UPDATED, (
        "once the rental is ended, Repair must be allowed — otherwise the two-step "
        "ADR-0009 asks for has no second step and a held laptop can never be "
        f"serviced. Got {after_recall.status_code}: {after_recall.text}"
    )


# --------------------------------------------------------------------------
# Deleting a held item (ADR-0011)
# --------------------------------------------------------------------------


def test_cannot_delete_a_held_item(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """Retiring a laptop somebody is holding is refused; retiring a returned one is not.

    The second half is the discriminating one, and it is the harder half to implement.
    "Refuse if any rental row mentions this item" passes the first assertion and makes
    every item that was *ever* rented permanently undeletable — so the inventory
    accumulates retired hardware forever, and the guard reads as correct in a demo
    where nothing has been returned yet. ADR-0011 draws the line at *active* rentals
    for exactly this reason, which is also why `rentals.item_id` cannot be a blunt
    `RESTRICT`.
    """
    before = statuses_by_id(admin_client)

    held = admin_client.delete(f"{HARDWARE_PATH}/{HELD_ITEM}")
    assert held.status_code == 409, (
        "deleting an item with an active rental must be refused with 409 — the row "
        f"that survives would point at nothing (ADR-0011); got {held.status_code}: "
        f"{held.text}"
    )
    assert SEED_RENTER_EMAIL in held.text, (
        "the reason names the holder, so the admin knows who to recall it from; got "
        f"{held.text!r}"
    )
    assert HELD_ITEM in statuses_by_id(admin_client), (
        "the refused delete must leave the item in the inventory; it is gone even "
        "though the request was answered with 409"
    )
    assert len(rental_rows(app, HELD_ITEM)) == 1, (
        "and it must leave the rental row alone"
    )

    rented = user_client.post(rent_path(FREE_ITEM))
    assert rented.status_code in ACCEPTED, f"setup: rent failed: {rented.text}"
    returned = user_client.post(return_path(FREE_ITEM))
    assert returned.status_code in ACCEPTED, f"setup: return failed: {returned.text}"

    retired = admin_client.delete(f"{HARDWARE_PATH}/{FREE_ITEM}")
    assert retired.status_code in DELETED, (
        f"an item whose rental has ended stays deletable, with its history intact "
        f"(ADR-0011). Got {retired.status_code}: {retired.text}. A guard that refuses "
        "on any rental row at all makes every item ever borrowed permanently "
        "un-retirable"
    )
    assert FREE_ITEM not in statuses_by_id(admin_client), (
        f"item {FREE_ITEM} is still listed after a successful delete"
    )
    assert len(statuses_by_id(admin_client)) == len(before) - 1, (
        "exactly one item may have left the inventory"
    )


# --------------------------------------------------------------------------
# Reseeding over live rentals (ADR-0011)
# --------------------------------------------------------------------------


def test_reseed_refuses_when_rentals_exist(
    app, database_path: Path, user_client: TestClient
) -> None:
    """`persist` refuses to truncate `hardware` once a rental exists, and says why.

    The README publishes `railway run … python -m scripts.seed` as a live operation.
    `seed_if_empty` guards the *boot* path on emptiness; nothing guarded the manual
    one, so "a restart destroys every rental" was reachable through the documented
    command instead of through a bug.

    **Read this test together with `test_storage.py::test_reseed_is_idempotent`, which
    stays green.** That one calls `persist` twice on one engine and requires the second
    call to succeed; this one requires it to refuse. Both can only be true if `persist`
    never writes a rental itself — the seed id 7 rental (ADR-0007) is created by the
    layer *above* `persist`, in `scripts/seed.py`, where the decision belongs.
    `app/storage.py`'s docstring says the module makes no decisions, and ADR-0008
    already refuses to put `rentals` SQL there for that reason. So `persist` stays a
    row-mover with one refusal bolted on, and the `rentals` table stays outside the
    `MetaData` whose replace semantics would otherwise reach it.

    Act 3 is the consequence of that decision and is not optional: `persist` has to
    survive an engine where `rentals` has **never been created**, which is exactly the
    engine `test_storage.py` builds. A refusal implemented as an unguarded
    `SELECT … FROM rentals` turns that whole module red with an `OperationalError`.
    """
    rented = user_client.post(rent_path(FREE_ITEM))

    report = _seed_report()
    engine = create_engine_for(f"sqlite:///{database_path}")

    refusal: Exception | None = None
    session = new_session(engine)
    try:
        persist(report, session)
    except Exception as error:  # noqa: BLE001 — the exception type is the implementer's
        refusal = error
    finally:
        session.rollback()
        session.close()

    assert refusal is not None, (
        "persist must refuse outright once a rental row exists (ADR-0011) — it "
        "returned normally, which means the documented reseed command truncates "
        "`hardware` under a live rental and reports success while doing it. This "
        f"database holds {len(rental_rows(app))} rental row(s): the seed's own "
        f"imported one (ADR-0007) plus whatever the employee's rent, which answered "
        f"{rented.status_code}, added"
    )
    assert "rental" in str(refusal).lower(), (
        "the refusal has to say what stopped it, because the person reading it is an "
        "operator at a terminal deciding whether to force it; got "
        f"{str(refusal)!r}"
    )

    reader = new_session(engine)
    survivors = load_items(reader)
    reader.close()
    assert len(survivors) == len(report.imported), (
        f"the refused reseed must leave every hardware item in place; the seed "
        f"imports {len(report.imported)} and the table now holds {len(survivors)}"
    )
    assert rented.status_code in ACCEPTED, (
        f"the employee's rent must have succeeded for the assertion below to be about "
        f"a live rental rather than only the seed's; it answered "
        f"{rented.status_code}: {rented.text}"
    )
    assert rental_rows(app, FREE_ITEM), (
        "and it must leave the rental itself in place; the row is gone"
    )

    untouched = create_engine_for(f"sqlite:///{database_path.parent / 'no_rentals.db'}")
    create_schema(untouched)
    control = new_session(untouched)
    persist(report, control)
    control.commit()
    reloaded = load_items(control)
    control.close()
    assert len(reloaded) == len(report.imported), (
        "control failed: persist must still work on a database with no rentals — and "
        "on one where the `rentals` table has never been created at all, which is the "
        "engine every test in test_storage.py builds. A refusal that queries `rentals` "
        "unconditionally raises OperationalError there and takes seven green tests "
        f"with it. Got {len(reloaded)} items"
    )
