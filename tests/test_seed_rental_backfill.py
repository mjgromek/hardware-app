"""Phase 2 — an item held on an existing volume must not be stranded.

Found by deploying v2 and trying the four flows against the live instance rather than a
fresh database. Seed id 7 reported `In Use`, and force-return answered "not currently
rented": the ADR-0007 rental is opened inside `seed_if_empty`, which returns early when
the hardware table is not empty — true of every database that existed before Phase 2.

So on an upgraded volume the item is held by an address with no account *and* no rental
row. Nobody can return it, because there is no rental to close. Nobody can recall it, for
the same reason. `CONTEXT.md` calls "In Use with no renter" an impossible state and the
importer already refuses to leave one; this is the same state arriving by a different
route — through a deploy rather than through the seed.

The fix has to be idempotent and run on every boot, not only on an empty database, which
is the opposite of how the seed is guarded. That asymmetry is the point: seeding *writes
inventory* and must never repeat, while this *reconciles* a row that already exists.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import rentals
from app.domain import Status
from app.main import create_app
from app.storage import (
    create_engine_for,
    create_schema,
    new_session,
    persist,
)
from scripts.seed import SEED_PATH, ingest
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, attempt_login
import json

HELD_ITEM = 7
SEED_RENTER_EMAIL = "j.doe@booksy.com"


def _env(database_url: str) -> dict[str, str]:
    return {
        "ENVIRONMENT": "development",
        "SECRET_KEY": "test-secret-key-not-the-real-one",
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "DATABASE_URL": database_url,
    }


def _database_seeded_the_phase_1_way(tmp_path: Path) -> str:
    """A volume as Phase 1 left it: hardware imported, no `rentals` table at all."""
    database_url = f"sqlite:///{tmp_path / 'upgraded.db'}"
    engine = create_engine_for(database_url)
    create_schema(engine)
    report = ingest(json.loads(SEED_PATH.read_text(encoding="utf-8")))
    with new_session(engine) as session:
        persist(report, session)
        session.commit()
    return database_url


def test_boot_backfills_a_rental_for_an_item_held_without_one(tmp_path: Path) -> None:
    """Booting Phase 2 over a Phase 1 database gives the held item its rental.

    The assertion that matters is not that a row appears — it is that the item becomes
    **actionable**. A backfilled row that nobody can act on would satisfy a
    "there is a rental now" check and leave the headphones exactly as stranded.
    """
    database_url = _database_seeded_the_phase_1_way(tmp_path)

    app = create_app(_env(database_url))

    engine = create_engine_for(database_url)
    with new_session(engine) as session:
        rental = rentals.active_rental(session, HELD_ITEM)

    assert rental is not None, (
        f"item {HELD_ITEM} is `In Use` on this volume and has no rental behind it, so "
        "nobody can return it and no admin can recall it. Boot has to reconcile that, "
        "because the seed path never runs again on a database that already has hardware"
    )
    assert rental.account_id is None, (
        "the backfilled rental belongs to an address with no account (ADR-0007), so its "
        f"account_id stays NULL; got {rental.account_id!r}"
    )
    assert rental.renter_email == SEED_RENTER_EMAIL, (
        f"the holder recorded on the item is the holder on the rental; got "
        f"{rental.renter_email!r}"
    )

    client = TestClient(app)
    assert attempt_login(client, ADMIN_EMAIL, ADMIN_PASSWORD).status_code in (200, 204)
    recalled = client.post(
        f"/api/hardware/{HELD_ITEM}/force-return",
        json={"reason": "Reconciled during the Phase 2 upgrade"},
    )
    assert recalled.status_code in (200, 201, 204), (
        "the whole point of the backfill is that the item can now be recalled; got "
        f"{recalled.status_code}: {recalled.text}"
    )


def test_backfill_does_not_run_twice_or_touch_free_items(tmp_path: Path) -> None:
    """Two boots leave one rental, and nothing is invented for an item nobody holds.

    The discriminating half is the second: a backfill written as "every `In Use` item
    gets a rental" would also fire for an item somebody rented and returned through the
    API, and one written without the idempotency check would open a fresh rental on
    every restart until the partial unique index refused — turning a redeploy into an
    error nobody expected.
    """
    database_url = _database_seeded_the_phase_1_way(tmp_path)

    create_app(_env(database_url))
    create_app(_env(database_url))

    engine = create_engine_for(database_url)
    with new_session(engine) as session:
        held = rentals.item_ids_held_by(session, account_id=None)
        rows = session.execute(
            rentals.rentals.select().where(rentals.rentals.c.item_id == HELD_ITEM)
        ).all()
        items = {
            item.id: item
            for item in __import__("app.storage", fromlist=["load_items"]).load_items(session)
        }

    assert len(rows) == 1, (
        f"two boots must leave one rental for item {HELD_ITEM}, not one per restart; "
        f"got {len(rows)}"
    )
    assert held == set(), (
        "the accountless rental belongs to no account, so an account-scoped query finds "
        f"nothing; got {held}"
    )
    available_ids = [i for i, item in items.items() if item.status is Status.AVAILABLE]
    with new_session(engine) as session:
        invented = [i for i in available_ids if rentals.active_rental(session, i)]
    assert not invented, (
        f"nothing may be invented for items nobody holds; got rentals on {invented}"
    )
