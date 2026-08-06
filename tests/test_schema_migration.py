"""Booting over a database created by an earlier phase must not fail.

This test exists because it did fail, in production. ADR-0013's `session_token` and
`deleted_at` were described as "additive columns backfilled on boot", and they are —
but `metadata.create_all()` **skips a table that already exists**, so nothing ever added
them to a live `users` table. The deploy came up, the first query touched
`users.deleted_at`, and the instance returned `502` until the next deploy.

The lesson is narrow and worth keeping: *additive* is a property of the column, not of the
code. A schema change needs something that actually runs against the existing table, and
`create_all` is not that thing.

Written against a `users` table built with raw SQL in exactly the shape Phase 1 shipped,
rather than by an older version of the app, so the test keeps meaning once the model moves
on again.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, attempt_login

#: `users` exactly as Phase 1 created it: no `session_token`, no `deleted_at`.
PHASE_1_USERS = """
CREATE TABLE users (
    id INTEGER NOT NULL,
    email VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (email)
)
"""


def _phase_1_database(tmp_path: Path) -> str:
    database_path = tmp_path / "phase1.db"
    connection = sqlite3.connect(database_path)
    connection.execute(PHASE_1_USERS)
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


def test_boot_adds_columns_missing_from_an_older_users_table(tmp_path: Path) -> None:
    """The app starts, and the account it bootstraps can actually sign in.

    "It booted" is not the assertion — the failure in production was a query at first
    request, not at startup, so a test that only calls `create_app` would have passed
    while the instance still answered `502` to every caller. Logging in exercises
    `verify_credentials`, `session_token_for` and `find_by_token`, which is every column
    the migration adds.
    """
    database_url = _phase_1_database(tmp_path)

    app = create_app(_env(database_url))

    client = TestClient(app)
    signed_in = attempt_login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert signed_in.status_code in (200, 204), (
        "an app booted over a pre-Phase-2 database must be usable, not merely running; "
        f"login returned {signed_in.status_code}: {signed_in.text}"
    )
    assert client.get("/api/users").status_code == 200, (
        "and the account listing must work — it reads the columns the migration added"
    )


def test_boot_is_idempotent_over_an_already_migrated_database(tmp_path: Path) -> None:
    """A second boot adds nothing and breaks nothing.

    `ALTER TABLE … ADD COLUMN` fails outright if the column is already there, so a
    migration that does not check would turn every restart after the first into the same
    `502` it was written to prevent — with the added charm of working exactly once.
    """
    database_url = _phase_1_database(tmp_path)

    create_app(_env(database_url))
    app = create_app(_env(database_url))

    client = TestClient(app)
    assert attempt_login(client, ADMIN_EMAIL, ADMIN_PASSWORD).status_code in (200, 204), (
        "the second boot must leave the database exactly as usable as the first"
    )
