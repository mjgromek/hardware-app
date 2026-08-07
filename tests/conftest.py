"""Phase 1 fixtures — an app with a bootstrapped admin, driven over HTTP.

Every Phase 1 test goes through ``TestClient`` rather than calling functions
directly, for one specific reason: **the authorization enforcement point is still
open** (`brainstorm.md` §7 — per-route dependency vs middleware, to be settled in
Phase 1's first commit). A test that imports a ``require_admin`` dependency, or one
that asserts a middleware ran, would decide that question by accident. A test that
sends a request and reads a status code does not care which mechanism refused it.

**The admin exists because the environment says so** (ADR-0005). No fixture writes
a user row: ``create_app`` is handed ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` and admin
#1 must exist afterwards, which is the bootstrap path the ADR specifies. Non-admin
accounts are created the only way the product allows — by an admin, over the API,
because there is no self-registration.

**One client per session, not one client per test.** ``TestClient`` keeps a cookie
jar, so logging in twice on one client would overwrite the first session. The admin
and the user hold separate clients over the *same* app, which is also what makes the
authorization tests honest: the user's client never had an admin cookie to begin
with.

## The HTTP contract these tests pin

Nothing in `brainstorm.md` or the ADRs fixes the request shapes, so this file does.
Recorded here rather than spread across four modules, because it is a decision and
it should be reviewable in one place (see `BACKLOG.md`).

| Route                                  | Who     | Meaning                              |
| -------------------------------------- | ------- | ------------------------------------ |
| ``POST   /api/login``                  | anyone  | ``{email, password}`` → session      |
| ``GET    /api/users``                  | admin   | accounts, as ``{id, email, role}``   |
| ``POST   /api/users``                  | admin   | ``{email, password, role}`` → account|
| ``PATCH  /api/users/{id}``             | admin   | ``{role}`` → promote / demote        |
| ``DELETE /api/users/{id}``             | admin   | remove an account                    |
| ``GET    /api/hardware``               | session | ``?sort=purchase_date``, ``?status=…``|
| ``PATCH  /api/hardware/{id}``          | admin   | ``{status}`` → toggle Repair         |
| ``DELETE /api/hardware/{id}``          | admin   | remove an item                       |
| ``POST /api/hardware/{id}/rent``       | session | claim it — ``Available`` → ``In Use``|
| ``POST /api/hardware/{id}/return``     | renter  | close **your own** rental            |
| ``POST /api/hardware/{id}/force-return``| admin  | ``{reason}`` → close anybody's       |
| ``POST /api/hardware/{id}/clear-review``| admin  | ``{reason}`` → clear ``needs_review``|

``GET /api/hardware`` **requires a session** — any role, admin or user. Only
admin-created accounts may use the Hub, so there is no anonymous read of the
inventory; the rule is pinned by ``test_auth.py::test_inventory_requires_a_session``
and three Phase 0 tests were amended to authenticate. ``GET /`` stays public, because
the login page has to be reachable by someone who is not logged in.

**Phase 2 makes that payload depend on the caller's role** (ADR-0012): ``notes``,
``history`` and ``review_reason`` are serialised for admins only, while renter
identity stays visible to every signed-in account. The four new routes above all take
a JSON body where one is listed and answer ``409`` — not ``400`` — when a guard
refuses them, because a refused rental is a well-formed permitted request that would
break an invariant, exactly as ADR-0005's last-admin refusal is.

Success codes are asserted permissively (``200`` or ``201``/``204``) because the
exact success code carries no product meaning. **Refusals are asserted exactly** —
``401`` unauthenticated, ``403`` authenticated-but-forbidden, ``409`` invariant
violated (ADR-0005) — because those distinctions are the behaviour under test.

## Reading `rentals` and `audit_events` without an HTTP surface

Slice A and B ship no read endpoint for either table — ``GET /api/hardware?held_by=me``
is Slice C, and Slice C is the first thing cut. So the two tests whose subject *is* the
recorded row (``test_rental_history_records_both_ends``,
``test_force_return_writes_an_audit_event``) read SQLite directly, through
``app.state.engine`` and raw SQL rather than through ``app.rentals``. Importing a module
that does not exist yet would make those tests *broken* rather than *red* (CONTEXT.md),
and every other Phase 2 test would go down with the import. The cost is that
``rental_rows`` and ``audit_rows`` pin the column names in `docs/specs/phase-2.md`'s
schema tables; that is the spec, and both helpers return ``[]`` for a table that is not
there yet so the failure still lands on the assertion that wanted the row. See
`BACKLOG.md` for retiring them once Slice C's filter exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.main import create_app

# Distinctive on purpose: `test_password_is_hashed_not_stored_plaintext` searches
# the database file for these strings, and "admin"/"password" would collide with
# column names, log lines and seed text.
ADMIN_EMAIL = "founding.admin@booksy.com"
ADMIN_PASSWORD = "bootstrap-admin-pw-9c41e7"

USER_EMAIL = "j.doe@booksy.com"
USER_PASSWORD = "regular-user-pw-4d17b2"

# A second ordinary employee. The wrong-renter guard (ADR-0009) is only testable
# with two of them, and it must be a `user` rather than the admin — an admin being
# refused the *ordinary* return verb is a different claim, asserted separately.
OTHER_USER_EMAIL = "s.novak@booksy.com"
OTHER_USER_PASSWORD = "other-user-pw-6e83a1"

LOGIN_PATH = "/api/login"
USERS_PATH = "/api/users"
HARDWARE_PATH = "/api/hardware"

#: Statuses success may be reported with. See the module docstring.
CREATED = (200, 201)
DELETED = (200, 204)
UPDATED = (200, 204)

#: How a request from nobody may be refused. Unauthenticated is `401`, but a
#: route that answers `403` has still refused it, and which of the two an
#: anonymous caller gets is not a product decision.
ANONYMOUS_REFUSAL = (401, 403)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """A database file this test alone can see, named so tests can read it back."""
    return tmp_path / "hardware_hub.db"


@pytest.fixture
def app(database_path: Path):
    """An app over a fresh database, with admin #1 bootstrapped from the environment.

    ``ENVIRONMENT`` is development so ``load_settings`` stays permissive, but
    ``ADMIN_EMAIL`` and ``ADMIN_PASSWORD`` are set explicitly rather than left to
    the development defaults — a test that logged in as ``admin``/``admin`` would
    pass against a hardcoded credential.
    """
    return create_app(
        {
            "ENVIRONMENT": "development",
            "SECRET_KEY": "test-secret-key-not-the-real-one",
            "ADMIN_EMAIL": ADMIN_EMAIL,
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
            "DATABASE_URL": f"sqlite:///{database_path}",
        }
    )


def attempt_login(client: TestClient, email: str, password: str):
    """Post credentials and hand back whatever came out. Asserts nothing.

    The failure tests need the raw response — status, body and cookies — so this
    helper deliberately does not judge it.
    """
    return client.post(LOGIN_PATH, json={"email": email, "password": password})


def log_in(client: TestClient, email: str, password: str) -> None:
    """Log ``client`` in, or fail loudly as a setup problem rather than a result."""
    response = attempt_login(client, email, password)
    assert response.status_code in (200, 204), (
        f"setup: {email} must be able to log in before a test can exercise what "
        f"that session may do; POST {LOGIN_PATH} returned "
        f"{response.status_code}: {response.text}"
    )


@pytest.fixture
def anonymous_client(app) -> TestClient:
    """A client that has never logged in."""
    return TestClient(app)


@pytest.fixture
def admin_client(app) -> TestClient:
    """A client logged in as admin #1, the account ADR-0005 bootstraps from env."""
    client = TestClient(app)
    log_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    return client


@pytest.fixture
def user_client(app, admin_client: TestClient) -> TestClient:
    """A client logged in as a ``user``-role account the admin created.

    There is no self-registration, so this goes through the admin's own endpoint.
    That the creation succeeds is the implicit control for
    ``test_non_admin_cannot_create_user``: if ``POST /api/users`` refused everyone,
    this fixture would fail rather than that test passing for the wrong reason.
    """
    response = admin_client.post(
        USERS_PATH,
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "role": "user"},
    )
    assert response.status_code in CREATED, (
        f"setup: an admin must be able to create a `user` account; POST "
        f"{USERS_PATH} returned {response.status_code}: {response.text}"
    )

    client = TestClient(app)
    log_in(client, USER_EMAIL, USER_PASSWORD)
    return client


@pytest.fixture
def other_user_client(app, admin_client: TestClient) -> TestClient:
    """A second ``user``-role client, so one employee can be told off for touching
    another employee's rental."""
    response = admin_client.post(
        USERS_PATH,
        json={"email": OTHER_USER_EMAIL, "password": OTHER_USER_PASSWORD, "role": "user"},
    )
    assert response.status_code in CREATED, (
        f"setup: an admin must be able to create a second `user` account; POST "
        f"{USERS_PATH} returned {response.status_code}: {response.text}"
    )

    client = TestClient(app)
    log_in(client, OTHER_USER_EMAIL, OTHER_USER_PASSWORD)
    return client


# --------------------------------------------------------------------------
# Phase 2 route shapes, named once
# --------------------------------------------------------------------------


def rent_path(item_id: int) -> str:
    return f"{HARDWARE_PATH}/{item_id}/rent"


def return_path(item_id: int) -> str:
    return f"{HARDWARE_PATH}/{item_id}/return"


def force_return_path(item_id: int) -> str:
    return f"{HARDWARE_PATH}/{item_id}/force-return"


def clear_review_path(item_id: int) -> str:
    return f"{HARDWARE_PATH}/{item_id}/clear-review"


def accounts_by_email(admin_client: TestClient) -> dict[str, dict]:
    """The account list, keyed by email — nothing may depend on its order."""
    response = admin_client.get(USERS_PATH)
    assert response.status_code == 200, (
        f"setup: GET {USERS_PATH} must list accounts for an admin, or a test "
        f"cannot address one by id; got {response.status_code}: {response.text}"
    )
    return {account["email"]: account for account in response.json()}


def statuses_by_id(client: TestClient) -> dict[int, str]:
    """Every hardware item's status, keyed by id."""
    response = client.get(HARDWARE_PATH)
    assert response.status_code == 200, (
        f"setup: GET {HARDWARE_PATH} must serve the inventory; got "
        f"{response.status_code}: {response.text}"
    )
    return {item["id"]: item["status"] for item in response.json()}


def items_by_id(client: TestClient) -> dict[int, dict]:
    """Every hardware item as the caller is allowed to see it, keyed by id.

    The whole payload rather than just the status, because ADR-0012 makes *which
    fields come back* role-dependent and ``statuses_by_id`` cannot see that.
    """
    response = client.get(HARDWARE_PATH)
    assert response.status_code == 200, (
        f"setup: GET {HARDWARE_PATH} must serve the inventory; got "
        f"{response.status_code}: {response.text}"
    )
    return {item["id"]: item for item in response.json()}


def _table_rows(app, table: str) -> list[dict[str, Any]]:
    """Every row of ``table``, or ``[]`` if the table does not exist yet.

    Deliberately tolerant of the missing table: before Slice A lands there is no
    ``rentals``, and a test that died of ``OperationalError`` would be broken rather
    than red. Returning nothing lets the caller's own "there must be one row here"
    assertion be what fails, which is the assertion the test exists to make.
    """
    engine = app.state.engine
    if table not in inspect(engine).get_table_names():
        return []
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(f"SELECT * FROM {table}")).mappings()]


def rental_rows(app, item_id: int | None = None) -> list[dict[str, Any]]:
    """The ``rentals`` table, optionally narrowed to one item.

    Filtered in Python rather than in SQL so that a table missing the ``item_id``
    column reports as "no rows for item N" instead of raising.
    """
    rows = _table_rows(app, "rentals")
    if item_id is None:
        return rows
    return [row for row in rows if row.get("item_id") == item_id]


def audit_rows(app, action: str | None = None) -> list[dict[str, Any]]:
    """The ``audit_events`` table (ADR-0010), optionally narrowed to one action."""
    rows = _table_rows(app, "audit_events")
    if action is None:
        return rows
    return [row for row in rows if row.get("action") == action]


def missing_columns(row: dict[str, Any], *expected: str) -> list[str]:
    """Which of ``expected`` the row does not carry.

    Asserted once, up front, before any value is read out of a row — so a schema that
    is missing a column fails saying *that*, rather than raising ``KeyError`` two
    lines later inside an assertion about something else.
    """
    return [name for name in expected if name not in row]


def issued_cookies(response) -> list[str]:
    """The ``Set-Cookie`` headers on ``response`` that actually set a value.

    A header clearing a cookie is not the issue of a session, so it is filtered
    out — otherwise "no session cookie was issued" would go red against an
    implementation that politely deletes a stale cookie on a failed login.
    """
    headers = response.headers.get_list("set-cookie")
    return [header for header in headers if _sets_a_value(header)]


def _sets_a_value(header: str) -> bool:
    _, _, value = header.split(";", 1)[0].partition("=")
    return value.strip(' "') != ""
