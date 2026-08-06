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

| Route                        | Who     | Meaning                                    |
| ---------------------------- | ------- | ------------------------------------------ |
| ``POST   /api/login``        | anyone  | ``{email, password}`` → session cookie     |
| ``GET    /api/users``        | admin   | accounts, as ``{id, email, role}``         |
| ``POST   /api/users``        | admin   | ``{email, password, role}`` → new account  |
| ``PATCH  /api/users/{id}``   | admin   | ``{role}`` → promote / demote              |
| ``DELETE /api/users/{id}``   | admin   | remove an account                          |
| ``GET    /api/hardware``     | session | ``?sort=purchase_date``, ``?status=…``     |
| ``PATCH  /api/hardware/{id}``| admin   | ``{status}`` → toggle Repair               |
| ``DELETE /api/hardware/{id}``| admin   | remove an item                             |

``GET /api/hardware`` **requires a session** — any role, admin or user. Only
admin-created accounts may use the Hub, so there is no anonymous read of the
inventory; the rule is pinned by ``test_auth.py::test_inventory_requires_a_session``
and three Phase 0 tests were amended to authenticate. ``GET /`` stays public, because
the login page has to be reachable by someone who is not logged in.

Success codes are asserted permissively (``200`` or ``201``/``204``) because the
exact success code carries no product meaning. **Refusals are asserted exactly** —
``401`` unauthenticated, ``403`` authenticated-but-forbidden, ``409`` invariant
violated (ADR-0005) — because those distinctions are the behaviour under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

# Distinctive on purpose: `test_password_is_hashed_not_stored_plaintext` searches
# the database file for these strings, and "admin"/"password" would collide with
# column names, log lines and seed text.
ADMIN_EMAIL = "founding.admin@booksy.example"
ADMIN_PASSWORD = "bootstrap-admin-pw-9c41e7"

USER_EMAIL = "j.doe@booksy.example"
USER_PASSWORD = "regular-user-pw-4d17b2"

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
