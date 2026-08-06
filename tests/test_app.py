"""Phase 0 — the application, wired end to end.

Single origin (ADR-0001): one FastAPI app serves both the JSON API and the built
Vue bundle. These tests are what make that wiring real rather than structural —
until now `create_app` mounted a directory that did not exist and exposed no data.

**Amended in Phase 1: `/api/hardware` requires a session.** The brief allows only
admin-created accounts into the Hub, so an inventory endpoint readable by anyone with
the URL contradicts it. Three tests in this file read that endpoint anonymously when
it was open, and they are amended here rather than in Phase 1's files, because the
change belongs where the requests are made. The trail is in `BACKLOG.md`; the rule
itself is pinned by `tests/test_auth.py::test_inventory_requires_a_session`.

The two boot-seed tests now read the database through `app.storage` instead of over
HTTP. That is deliberate. Their subject is *what boot did to the table*, and adding a
login to them would have made every future auth regression fail two seeding tests as
well — and would have made them unrunnable until login exists, for a property that
has nothing to do with login. Nothing is lost: that the seeded rows also reach the
wire is `test_api_returns_hardware_items`'s job, and it still does it over HTTP.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.domain import Status
from app.main import create_app
from app.storage import (
    create_engine_for,
    create_schema,
    load_items,
    new_session,
    persist,
)
from scripts.seed import ingest
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, log_in

TODAY = date(2026, 8, 6)
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed.json"


def _env(database_url: str) -> dict[str, str]:
    """A development environment with a known admin credential (ADR-0005).

    The admin is bootstrapped from the environment rather than written by a fixture,
    so a test that needs a session gets one the same way a deployment does.
    """
    return {
        "ENVIRONMENT": "development",
        "SECRET_KEY": "test-secret-key-not-the-real-one",
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "DATABASE_URL": database_url,
    }


def _items_in(database_url: str):
    """Read the hardware table directly, without going through the app.

    Used by the boot-seed tests: what boot wrote to the table is a question about
    the table, and answering it over an authenticated HTTP request would drag the
    auth layer into two tests that are not about it.
    """
    engine = create_engine_for(database_url)
    session = new_session(engine)
    try:
        return load_items(session)
    finally:
        session.close()


def _app_with_seeded_database(tmp_path: Path):
    """An app over a freshly seeded database file of its own."""
    database_url = f"sqlite:///{tmp_path / 'hardware_hub.db'}"

    engine = create_engine_for(database_url)
    create_schema(engine)
    session = new_session(engine)
    persist(ingest(json.loads(SEED_PATH.read_text(encoding="utf-8")), today=TODAY), session)
    session.commit()
    session.close()

    return create_app(_env(database_url))


def test_api_returns_hardware_items(tmp_path: Path) -> None:
    """The API serves the imported inventory to a signed-in caller, statuses intact.

    Eleven rows in the seed, eleven items on the wire — the same loss-free
    property the storage tests pin, asserted at the boundary a browser actually
    sees.

    The session is what changed in Phase 1. The endpoint is no longer public, so
    this test logs in first; what it asserts afterwards is exactly what it asserted
    before. The complementary rule — that *without* a session the same request is
    refused — is not asserted here, because a test that pins both "signed-in callers
    see the inventory" and "anonymous callers do not" goes red without saying which
    half broke. It lives in `test_auth.py::test_inventory_requires_a_session`.
    """
    client = TestClient(_app_with_seeded_database(tmp_path))
    log_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    response = client.get("/api/hardware")

    assert response.status_code == 200, response.text
    items = response.json()
    assert len(items) == 11, (
        f"the seed's 11 rows must all reach the API; got {len(items)}"
    )

    by_name = {item["name"]: item for item in items}
    assert by_name["Dell XPS 15 9510"]["status"] == "Available", (
        "status must survive to the client as one of the three enum values"
    )
    assert by_name["iPad Pro 12.9"]["brand"] == "Appel", (
        "the brand typo is the auditor's to surface, not ingestion's to correct "
        "(ADR-0002), so it must still be visible in the API"
    )
    assert by_name["Unknown Device"]["needs_review"] is True, (
        "needs_review is a rentability guard (ADR-0003), so the client has to be "
        "able to see it"
    )


def test_serves_built_bundle_at_root(tmp_path: Path) -> None:
    """``/`` returns the built Vue bundle, not a 404 and not a hand-written page.

    The single-origin mount (ADR-0001) was structurally present but unexercised —
    ``frontend/dist`` did not exist, so the conditional mount silently did nothing
    and no test would have noticed.

    Asserting on the ``/assets/`` reference rather than on any markup is what makes
    this a test of the *built* bundle: Vite emits hashed asset paths, so a
    placeholder ``index.html`` committed by hand would not satisfy it.
    """
    client = TestClient(_app_with_seeded_database(tmp_path))

    response = client.get("/")

    assert response.status_code == 200, (
        "the built bundle must be served at the root; got "
        f"{response.status_code}. Has `npm run build` been run in frontend/?"
    )
    assert response.headers["content-type"].startswith("text/html")
    assert "/assets/" in response.text, (
        "the served page must reference Vite's hashed assets, or what is mounted "
        "is not a built bundle"
    )


# --------------------------------------------------------------------------
# Boot-time seeding, guarded by emptiness
# --------------------------------------------------------------------------


def _app_over(database_url: str):
    """An app over a database this test controls, with no seeding done first."""
    return create_app(_env(database_url))


def test_boot_seeds_an_empty_database(tmp_path: Path, caplog) -> None:
    """A fresh database is seeded at startup, so a new deploy is not blank.

    This exists because the deploy target has no way to run a one-off command in
    the container. It is a deploy shim, not a migration strategy — see BACKLOG.md.

    Boot happens inside ``create_app``, so there is no request to make: the table is
    read directly afterwards. Since Phase 1 put ``/api/hardware`` behind a session,
    fetching it here would have meant logging in to answer a question about seeding —
    coupling this test to the auth layer for nothing. What it claims is unchanged:
    eleven rows in the table after a boot over an empty database.
    """
    database_url = f"sqlite:///{tmp_path / 'hardware_hub.db'}"

    with caplog.at_level(logging.INFO):
        _app_over(database_url)

    items = _items_in(database_url)
    assert len(items) == 11, (
        f"an empty database is seeded from data/seed.json at boot; got {len(items)}"
    )
    assert "seeded" in caplog.text.lower(), (
        f"boot must say which branch it took; log was {caplog.text!r}"
    )


def test_boot_leaves_a_populated_database_untouched(tmp_path: Path, caplog) -> None:
    """A database with any rows in it is never re-seeded.

    **This is the assertion that makes seed-on-boot safe.** Once the rental engine
    exists the table is never empty, so this branch is the one that runs on every
    real deploy — and re-seeding would silently destroy every rental, because
    persist has replace semantics.

    Read from the table rather than over HTTP, for the reason given in
    ``test_boot_seeds_an_empty_database``. It also makes the claim slightly sharper:
    the row that must survive is asserted where it has to survive, in SQLite, rather
    than as whatever a serialiser chose to emit.
    """
    database_url = f"sqlite:///{tmp_path / 'hardware_hub.db'}"

    engine = create_engine_for(database_url)
    create_schema(engine)
    session = new_session(engine)
    persist(ingest([{
        "id": 1,
        "name": "Only Item",
        "brand": "Acme",
        "purchaseDate": "2024-01-01",
        "status": "In Use",
        "assignedTo": "someone@booksy.com",
    }], today=TODAY), session)
    session.commit()
    session.close()

    with caplog.at_level(logging.INFO):
        _app_over(database_url)

    items = _items_in(database_url)
    assert len(items) == 1, (
        "a populated database must be left exactly as it was: re-seeding replaces "
        f"the whole table and would destroy live data; got {len(items)} items"
    )
    assert items[0].name == "Only Item", (
        f"the existing row must survive boot untouched; got {items[0].name!r}"
    )
    assert items[0].status is Status.IN_USE, (
        "the existing row's state must survive boot — this is the rental the guard "
        f"exists to protect; got {items[0].status!r}"
    )
    assert "skip" in caplog.text.lower(), (
        f"boot must say which branch it took; log was {caplog.text!r}"
    )
