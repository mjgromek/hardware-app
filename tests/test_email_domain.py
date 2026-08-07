"""Only `@booksy.com` addresses may be created (ADR-0019).

The interesting part of this rule is not the rejection — it is *where* the rule lives.
ADR-0019 chose creation-time, at the API boundary, and rejected a login-time check, whose
only distinctive power is to lock out accounts that predate the rule. It also chose to
have **no exemption** for the bootstrap admin, on the grounds that `bootstrap_admin` does
not travel through `POST /api/users` at all, so the exemption is structural rather than a
special case somebody has to remember.

Both of those are claims about structure, and structural claims decay silently. If someone
later routes `bootstrap_admin` through the validated path, or moves validation down into
`accounts.create_account`, a deployment whose `ADMIN_EMAIL` is off-domain stops booting —
with no admin, and therefore no way in, since `reset-demo` and account management are both
admin-only. `test_the_bootstrap_path_is_not_subject_to_domain_validation` is here to fail
loudly at that moment rather than on somebody's deploy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import status

from app import accounts
from app.accounts import create_schema as create_account_schema
from app.config import DEVELOPMENT_DEFAULTS
from app.storage import create_engine_for, new_session


ALLOWED_DOMAIN = "@booksy.com"


@pytest.fixture
def session(tmp_path: Path):
    """A database with the accounts schema and nothing in it.

    Deliberately not the `app` fixture: `create_app` bootstraps an admin on boot, and a
    database that already has one would make `bootstrap_admin` return `None` for the
    reason this test is not asking about.
    """
    engine = create_engine_for(f"sqlite:///{tmp_path / 'accounts.db'}")
    create_account_schema(engine)
    opened = new_session(engine)
    yield opened
    opened.close()


@pytest.mark.parametrize(
    "email",
    [
        "newhire@gmail.com",
        "contractor@example.org",
        "attacker@booksy.com.evil.net",  # the domain as a prefix of another
        "someone@notbooksy.com",  # the domain as a suffix of another
        "someone@BOOKSY.COM.attacker.io",
        "nodomainatall",
        "@booksy.com",  # the domain with no local part
    ],
)
def test_an_address_outside_the_company_domain_is_refused_at_creation(
    admin_client, email
) -> None:
    """Creation is the only gate, so it has to hold against near-misses.

    The two suffix/prefix cases are the ones a naive `in` or `startswith` check waves
    through, and both are registrable domains an outsider can actually own.
    """
    response = admin_client.post(
        "/api/users",
        json={"email": email, "password": "a-real-password", "role": "user"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, (
        f"{email!r} was accepted; only {ALLOWED_DOMAIN} addresses may be created"
    )

    listed = admin_client.get("/api/users").json()
    assert email not in [account["email"] for account in listed], (
        f"{email!r} was refused with the right status but stored anyway"
    )


def test_a_company_address_is_accepted(admin_client) -> None:
    response = admin_client.post(
        "/api/users",
        json={
            "email": "new.starter@booksy.com",
            "password": "a-real-password",
            "role": "user",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()["email"] == "new.starter@booksy.com"


def test_the_domain_check_is_case_insensitive(admin_client) -> None:
    """`New.Starter@Booksy.com` is the same mailbox; a rule that says otherwise is a bug.

    Domains are case-insensitive, and a person typing their own address with capitals is
    not an attack. Refusing it teaches admins the rule is arbitrary.
    """
    response = admin_client.post(
        "/api/users",
        json={
            "email": "New.Starter@Booksy.com",
            "password": "a-real-password",
            "role": "user",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text


def test_the_bootstrap_path_is_not_subject_to_domain_validation(session) -> None:
    """The exemption ADR-0019 calls structural, pinned so it stays structural.

    `bootstrap_admin` reads `ADMIN_EMAIL` from the environment — a trusted value set by
    whoever owns the deployment — and creates the account directly. It never crosses the
    API boundary where the rule lives, so an off-domain `ADMIN_EMAIL` must still boot.

    This is the lockout ADR-0019 was written to avoid: if this test ever fails, an
    existing deployment with an off-domain admin cannot start, and there is no admin
    left to fix it with.
    """
    created = accounts.bootstrap_admin(
        session, "admin@hardwarehub.internal", "a-real-password"
    )

    assert created is not None, "the bootstrap admin was refused for its domain"
    assert created.email == "admin@hardwarehub.internal"
    assert (
        accounts.verify_credentials(
            session, "admin@hardwarehub.internal", "a-real-password"
        )
        is not None
    ), "the bootstrap admin was created but cannot log in"


def test_the_shipped_default_admin_address_satisfies_the_rule(session) -> None:
    """The check ADR-0019 performed by hand, now performed on every run.

    ADR-0019's whole argument rests on there being no address in the project the rule
    would reject. `DEVELOPMENT_DEFAULTS` is the one that can drift back: it was
    `admin@localhost` until Phase 4, and reverting it is a one-token edit that no other
    test would notice.
    """
    for key in ("ADMIN_EMAIL", "DEMO_EMAIL"):
        assert DEVELOPMENT_DEFAULTS[key].lower().endswith(ALLOWED_DOMAIN), (
            f"{key} defaults to {DEVELOPMENT_DEFAULTS[key]!r}, which the creation rule "
            f"would reject — ADR-0019 requires every account in the project to sit on "
            f"{ALLOWED_DOMAIN}"
        )
