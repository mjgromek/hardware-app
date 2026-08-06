"""Phase 0 — the application, wired end to end.

Single origin (ADR-0001): one FastAPI app serves both the JSON API and the built
Vue bundle. These two tests are what make that wiring real rather than structural —
until now `create_app` mounted a directory that did not exist and exposed no data.

Both go through an HTTP client rather than calling functions directly. The mount
order, the route paths and the static fallback are exactly the things that only
misbehave over HTTP.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import create_engine_for, create_schema, new_session, persist
from scripts.seed import ingest

TODAY = date(2026, 8, 6)
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed.json"


def _app_with_seeded_database(tmp_path: Path):
    """An app over a freshly seeded database file of its own."""
    database_url = f"sqlite:///{tmp_path / 'hardware_hub.db'}"

    engine = create_engine_for(database_url)
    create_schema(engine)
    session = new_session(engine)
    persist(ingest(json.loads(SEED_PATH.read_text(encoding="utf-8")), today=TODAY), session)
    session.commit()
    session.close()

    return create_app({"ENVIRONMENT": "development", "DATABASE_URL": database_url})


def test_api_returns_hardware_items(tmp_path: Path) -> None:
    """The API serves the imported inventory, statuses intact.

    Eleven rows in the seed, eleven items on the wire — the same loss-free
    property the storage tests pin, asserted at the boundary a browser actually
    sees.
    """
    client = TestClient(_app_with_seeded_database(tmp_path))

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
    return create_app({"ENVIRONMENT": "development", "DATABASE_URL": database_url})


def test_boot_seeds_an_empty_database(tmp_path: Path, caplog) -> None:
    """A fresh database is seeded at startup, so a new deploy is not blank.

    This exists because the deploy target has no way to run a one-off command in
    the container. It is a deploy shim, not a migration strategy — see BACKLOG.md.
    """
    database_url = f"sqlite:///{tmp_path / 'hardware_hub.db'}"

    with caplog.at_level(logging.INFO):
        client = TestClient(_app_over(database_url))

    items = client.get("/api/hardware").json()
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
        client = TestClient(_app_over(database_url))

    items = client.get("/api/hardware").json()
    assert len(items) == 1, (
        "a populated database must be left exactly as it was: re-seeding replaces "
        f"the whole table and would destroy live data; got {len(items)} items"
    )
    assert items[0]["name"] == "Only Item", (
        f"the existing row must survive boot untouched; got {items[0]['name']!r}"
    )
    assert items[0]["status"] == "In Use", (
        "the existing row's state must survive boot — this is the rental the guard "
        f"exists to protect; got {items[0]['status']!r}"
    )
    assert "skip" in caplog.text.lower(), (
        f"boot must say which branch it took; log was {caplog.text!r}"
    )
