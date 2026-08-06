"""Phase 1 — the published demo credentials have to work on a fresh volume.

`mvp-reviewer` found that `demo@booksy.com` existed only inside the Railway volume, created
once by hand. Nothing in the code, the environment or the seed creates it — so the day that
volume is replaced, the README goes on publishing credentials that no longer exist and a
reviewer meets a login screen that rejects the only password they have. That is the worst
possible first impression, and it fails silently: the app boots fine.

So the demo account is bootstrapped like admin #1 (ADR-0005), under the same emptiness
guard as the hardware seed: it is created only when the database has no accounts at all. A
restart must never resurrect an account somebody deliberately deleted, and must never
reset a password somebody has since changed.

It is a `user`, not an admin. `/security-review` established that publishing an admin
credential on a public instance hands every reader delete rights over the inventory.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import accounts
from app.main import create_app
from app.storage import create_engine_for, new_session
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, HARDWARE_PATH, USERS_PATH, attempt_login

DEMO_EMAIL = "demo@booksy.com"
DEMO_PASSWORD = "hardware-hub-demo"


def _env(database_url: str) -> dict[str, str]:
    return {
        "ENVIRONMENT": "development",
        "SECRET_KEY": "test-secret-key-not-the-real-one",
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "DATABASE_URL": database_url,
    }


def test_boot_creates_the_published_demo_account(tmp_path: Path) -> None:
    """A fresh database gets the demo account, and the README's password works.

    The password is asserted by *logging in with it*, not by checking a row exists. The
    failure this test exists to prevent is "the documented credentials do not work", and
    only a login proves they do — a row with a different password satisfies every other
    check.

    Its role is asserted too. An admin demo account is the exposure `/security-review`
    removed, and a bootstrap that quietly recreated it as admin would undo that fix on the
    next fresh deploy.
    """
    database_url = f"sqlite:///{tmp_path / 'hardware_hub.db'}"
    client = TestClient(create_app(_env(database_url)))

    signed_in = attempt_login(client, DEMO_EMAIL, DEMO_PASSWORD)
    assert signed_in.status_code in (200, 204), (
        f"the demo credentials published in the README must work on a fresh database; "
        f"POST /api/login returned {signed_in.status_code}: {signed_in.text}. A reviewer "
        "meeting this is the first thing they see of the project"
    )
    assert signed_in.json()["role"] == "user", (
        "the demo account must be a `user`: /security-review cut it from admin precisely "
        f"because published admin credentials grant delete rights; got {signed_in.json()!r}"
    )

    assert client.get(HARDWARE_PATH).status_code == 200, (
        "the demo account must be able to read the inventory, or it demonstrates nothing"
    )
    assert client.get(USERS_PATH).status_code == 403, (
        "and must be refused the admin routes — a published credential that can delete "
        "the account list is the hole this account was demoted to close"
    )


def test_boot_leaves_an_existing_database_alone(tmp_path: Path) -> None:
    """A database that already has accounts is not touched.

    Two failures guarded here, and the second is the dangerous one. A bootstrap that ran
    unconditionally would **resurrect a deleted demo account** on the next restart, so
    revoking it would be impossible; and it would **reset its password**, silently undoing
    a rotation. The emptiness guard is what makes boot-time account creation safe, exactly
    as it does for the hardware seed.
    """
    database_url = f"sqlite:///{tmp_path / 'hardware_hub.db'}"
    create_app(_env(database_url))  # first boot creates admin #1 and the demo account

    engine = create_engine_for(database_url)
    with new_session(engine) as session:
        demo = next(a for a in accounts.list_accounts(session) if a.email == DEMO_EMAIL)
        accounts.delete_account(session, demo.id)
        session.commit()

    create_app(_env(database_url))  # second boot must not undo that

    with new_session(engine) as session:
        emails = [account.email for account in accounts.list_accounts(session)]
    assert DEMO_EMAIL not in emails, (
        "a deliberately deleted demo account must stay deleted across a restart — if boot "
        f"recreates it, the account cannot be revoked at all; accounts are {emails}"
    )
    assert ADMIN_EMAIL in emails, (
        "and the admin must survive, or the emptiness guard is doing something else"
    )
