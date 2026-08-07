"""Phase 4's columns, added to a `hardware` table that already exists.

The companion to `tests/test_schema_migration.py`, which makes this argument once for
`users` and is worth not repeating: `metadata.create_all()` **skips a table that
already exists**, so nothing it does will ever add a column to a live volume. Phase 2
shipped that defect and the instance answered `502` until the next deploy.

`hardware` is the worse case. The `users` table could be rebuilt from the environment
in a pinch — admin #1 is bootstrapped from `ADMIN_EMAIL` on every boot. `hardware`
cannot: the volume holds items an admin typed in and rentals pointing at them
(ADR-0011), so a migration that drops and recreates the table to get its new shape
destroys production data while passing every test that builds its database from
scratch.

The Phase 3 shape is written out in raw SQL rather than produced by an older checkout,
so these tests keep their meaning after the model moves on again.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    HARDWARE_PATH,
    attempt_login,
    missing_columns,
)

#: `hardware` exactly as Phase 3 left it: no `serial_number`, no `category`,
#: no `date_added`.
PHASE_3_HARDWARE = """
CREATE TABLE hardware (
    id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    brand VARCHAR,
    purchase_date DATE,
    status VARCHAR NOT NULL,
    source_id INTEGER,
    needs_review BOOLEAN NOT NULL,
    review_reason TEXT,
    notes TEXT,
    history TEXT,
    assigned_to VARCHAR,
    PRIMARY KEY (id)
)
"""

#: A row that was on the volume before Phase 4 — an item an admin added by hand, which
#: no reseed would ever put back. `seed_if_empty` skips a non-empty table, so inserting
#: this is also what makes the test exercise the *upgrade* path rather than a fresh seed.
LIVE_ROW = {
    "id": 1,
    "name": "Dell Latitude 5420",
    "brand": "Dell",
    "purchase_date": "2022-04-11",
    "status": "Available",
    "needs_review": 0,
}


def _phase_3_database(tmp_path: Path, *rows: dict[str, Any]) -> str:
    database_path = tmp_path / "phase3.db"
    connection = sqlite3.connect(database_path)
    connection.execute(PHASE_3_HARDWARE)
    for row in rows:
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        connection.execute(
            f"INSERT INTO hardware ({columns}) VALUES ({placeholders})", tuple(row.values())
        )
    connection.commit()
    connection.close()
    return f"sqlite:///{database_path}"


def _env(database_url: str) -> dict[str, str]:
    return {
        "ENVIRONMENT": "development",
        "SECRET_KEY": "test-secret-key-not-the-real-one",
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "DATABASE_URL": database_url,
    }


def _signed_in(app) -> TestClient:
    client = TestClient(app)
    signed_in = attempt_login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert signed_in.status_code in (200, 204), (
        "an app booted over a pre-Phase-4 database must be usable, not merely running; "
        f"login returned {signed_in.status_code}: {signed_in.text}"
    )
    return client


def _inventory(client: TestClient) -> list[dict[str, Any]]:
    response = client.get(HARDWARE_PATH)
    assert response.status_code == 200, (
        f"GET {HARDWARE_PATH} must serve the inventory over an upgraded database — "
        "this is the request that returned 502 in production, at the first query "
        f"touching a column the migration never added; got {response.status_code}: "
        f"{response.text}"
    )
    return response.json()


def test_boot_over_a_phase_3_hardware_table_serves_the_new_columns(tmp_path: Path) -> None:
    """The app starts over an older `hardware` table and can still list it.

    "It booted" is not the assertion. The Phase 2 failure was a query at first request,
    not at startup, so a test that only called `create_app` would have passed while
    every caller got a `502`. Logging in and reading the inventory is what touches
    `serial_number`, `category` and `date_added` in a real `SELECT`.
    """
    app = create_app(_env(_phase_3_database(tmp_path)))

    items = _inventory(_signed_in(app))
    assert items, (
        "an empty pre-Phase-4 table is seeded on boot, so the inventory must not be "
        "empty — with no rows this test could not see a missing column at all"
    )

    incomplete = {
        item["id"]: missing_columns(item, "serial_number", "category", "date_added")
        for item in items
    }
    assert not any(incomplete.values()), (
        "every item served from an upgraded database must carry the Phase 4 columns; "
        f"missing: { {k: v for k, v in incomplete.items() if v} }"
    )


def test_migration_keeps_rows_that_predate_the_new_columns(tmp_path: Path) -> None:
    """An item already on the volume survives the upgrade, and gets dated from it.

    Two failures in one place because they are the same mistake seen from either end.
    A migration that recreates `hardware` to change its shape passes the test above —
    the new columns are certainly there — while having deleted every item an admin
    ever added and orphaned every rental pointing at one (ADR-0011). And a migration
    that adds the columns but backfills nothing leaves the live rows with a null
    `date_added`, which is the state no fresh-database test can reach.
    """
    app = create_app(_env(_phase_3_database(tmp_path, LIVE_ROW)))

    items = {item["id"]: item for item in _inventory(_signed_in(app))}
    survivor = items.get(LIVE_ROW["id"])
    assert survivor is not None, (
        f"the item already on the volume must survive the upgrade; the inventory "
        f"holds {sorted(items)}"
    )
    assert survivor["name"] == LIVE_ROW["name"], (
        f"and survive intact, not as a reseeded namesake; got {survivor['name']!r}"
    )
    assert survivor["status"] == LIVE_ROW["status"], (
        f"with its status untouched; got {survivor['status']!r}"
    )

    absent = missing_columns(survivor, "serial_number", "category", "date_added")
    assert not absent, f"the surviving row is missing {absent}; got {survivor}"
    assert survivor["date_added"] is not None, (
        "a row that predates the column must be backfilled, not left null — the whole "
        "inventory would sort as undated on the first screen that uses it"
    )
    assert (
        datetime.fromisoformat(survivor["date_added"].replace("Z", "+00:00")).date()
        == date.fromisoformat(LIVE_ROW["purchase_date"])
    ), (
        "and backfilled from the date the row already carried, not from the day of the "
        f"deploy; purchase_date {LIVE_ROW['purchase_date']}, date_added "
        f"{survivor['date_added']}"
    )


def test_boot_is_idempotent_over_an_already_migrated_hardware_table(tmp_path: Path) -> None:
    """A second boot adds nothing and breaks nothing.

    `ALTER TABLE … ADD COLUMN` fails outright if the column is already there, so a
    migration that does not check turns every restart after the first into the same
    `502` it was written to prevent — with the added charm of working exactly once,
    which is to say working in staging and failing on the deploy after.
    """
    database_url = _phase_3_database(tmp_path, LIVE_ROW)

    create_app(_env(database_url))
    app = create_app(_env(database_url))

    items = {item["id"]: item for item in _inventory(_signed_in(app))}
    assert LIVE_ROW["id"] in items, (
        "the second boot must leave the database exactly as usable as the first; the "
        f"pre-existing item is gone, inventory holds {sorted(items)}"
    )
    assert not missing_columns(items[LIVE_ROW["id"]], "serial_number", "category", "date_added"), (
        "and the columns the first boot added must still be served after the second"
    )
