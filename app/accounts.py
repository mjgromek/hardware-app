"""Accounts — who exists, and whether a submitted password belongs to them.

The password digest never leaves this module. Callers hand in a credential and get
back an ``Account`` or nothing; there is no accessor for the stored hash, which is
what makes "the API must not echo the password" a property of the type rather than a
rule someone has to remember (see ``domain.Account``).

**Standard library only**, like ``app.config`` and for a related reason: the
credential path should be readable without trusting a third-party dependency, and
``hashlib.scrypt`` is in the standard library precisely for this.

Table shape lives here rather than in ``app.storage``. Storage is the seed pipeline's
persistence — it has replace semantics (a reseed truncates ``hardware``), and an
account table inside that boundary would be one refactor away from being wiped by a
reseed. Separate metadata, separate ``create_schema``, no shared truncation.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.orm import Session

from app.domain import Account, Role

__all__ = [
    "create_schema",
    "hash_password",
    "verify_credentials",
    "create_account",
    "find_by_id",
    "find_by_token",
    "session_token_for",
    "backfill_session_tokens",
    "new_session_token",
    "list_accounts",
    "count_admins",
    "set_role",
    "delete_account",
    "bootstrap_admin",
    "bootstrap_demo",
    "has_no_accounts",
    "EmailAlreadyExists",
]

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # Unique at the database level, not only in a handler: two rows with one address
    # makes "which account is this" unanswerable, and a login that resolves it by
    # picking the first row is a lottery over privilege.
    Column("email", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("role", String, nullable=False),
    #: What a session cookie actually names. Nullable only so the column can be added
    #: to a live database and backfilled; every account has one after boot.
    #:
    #: **A row id is a storage detail, and using it as session identity turns storage
    #: decisions into security decisions.** `users.id` is a SQLite rowid alias, so it is
    #: recycled when the highest-id account is deleted — and a cookie naming an id then
    #: silently reattaches to whoever inherits it, which `/security-review` demonstrated
    #: turning a deleted `user` into a live admin. A random token is issued once, never
    #: reissued, and matches nothing after its account is gone.
    Column("session_token", String, nullable=True, unique=True),
    #: When this account was removed, or ``NULL`` while it is live. **The row is never
    #: deleted**, which is what keeps its id out of circulation: `users.id` is a SQLite
    #: rowid alias, so removing the highest row frees its number for the next account —
    #: and `audit_events.actor_account_id` and closed `rentals.account_id` both point at
    #: that number. A departed admin's actions would become attributable to whoever
    #: inherited it (ADR-0013).
    Column("deleted_at", DateTime, nullable=True),
)

#: Live accounts only. Every read on the authentication and listing paths carries this,
#: because a soft-deleted row must behave as if it were gone everywhere except history.
_LIVE = users.c.deleted_at.is_(None)

#: scrypt cost. 2**14 with r=8 needs ~16 MB and takes ~50 ms — slow enough that a
#: stolen database file is not a wordlist away from being credentials, fast enough
#: that a login is not a visible pause. Stored per-hash so raising it later does not
#: invalidate existing rows.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1

#: `hash_password` output: algorithm, its parameters, the salt, the digest. Parsing
#: the parameters back out of the row is what makes the cost above a default rather
#: than a permanent commitment.
_FORMAT = "scrypt${n}${r}${p}${salt}${digest}"


class EmailAlreadyExists(ValueError):
    """Raised when an account already holds the requested address."""


#: Columns added after the users table first shipped, in the order they arrived. SQLite
#: refuses `ADD COLUMN` with a `UNIQUE` constraint, so `session_token`'s uniqueness is a
#: separate index — which `create_all` also builds for a fresh database, so both paths
#: end in the same shape.
_ADDED_COLUMNS = (
    ("session_token", "VARCHAR"),
    ("deleted_at", "DATETIME"),
)


def create_schema(engine: Engine) -> None:
    """Create the users table if it is absent, and bring an older one up to date.

    **`metadata.create_all` skips a table that already exists**, columns and all. That is
    the whole reason this function has a second half: ADR-0013's columns were described as
    "additive, backfilled on boot" and they are — but nothing was adding them to a live
    `users` table, so the deploy came up and every request touching `deleted_at` answered
    `502`. *Additive* is a property of the column, not of the code.

    Idempotent by inspection rather than by exception: `ADD COLUMN` fails outright if the
    column is present, so a migration that did not check would work exactly once and turn
    every restart after it into the same outage.
    """
    metadata.create_all(engine)

    with engine.begin() as connection:
        existing = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(users)")).all()
        }
        for column, sql_type in _ADDED_COLUMNS:
            if column not in existing:
                connection.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column} {sql_type}")
                )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_session_token "
                "ON users (session_token)"
            )
        )


def hash_password(password: str) -> str:
    """Derive a salted scrypt digest for ``password``.

    **A fresh 16-byte salt per call**, so two accounts choosing the same password
    store different digests and one precomputed table cannot answer for both. This
    is the difference the tests look for: an unsalted SHA-256 of a password is a
    lookup away from the plaintext, and a database file lives on a persistent volume.
    """
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt)
    return _FORMAT.format(
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        salt=salt.hex(),
        digest=digest.hex(),
    )


def _derive(password: str, salt: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p)


def _matches(password: str, stored: str) -> bool:
    """Whether ``password`` derives to ``stored``, in constant time.

    A malformed or unrecognised stored value is a mismatch rather than an exception:
    a single corrupt row should refuse one login, not 500 the endpoint for everyone.
    """
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = _derive(password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, actual)


#: Burned when an email has no account, so that a request for an address that does
#: not exist costs the same as one for an address that does. Without it the endpoint
#: answers "no such account" measurably faster than "wrong password", which
#: enumerates accounts through a side channel the identical response bodies close.
_ABSENT_ACCOUNT_HASH = hash_password("no account holds this address")


def verify_credentials(session: Session, email: str, password: str) -> Account | None:
    """The account these credentials belong to, or ``None``.

    One function for the whole question, because splitting it into "does this email
    exist" and "is this the password" invites a caller to answer the first out loud —
    which is exactly the enumeration the login endpoint must not offer.
    """
    row = session.execute(
        select(users).where(users.c.email == email, _LIVE)
    ).mappings().one_or_none()

    if row is None:
        _matches(password, _ABSENT_ACCOUNT_HASH)
        return None
    if not _matches(password, row["password_hash"]):
        return None
    return _account(row)


def new_session_token() -> str:
    """A session identity that no future account can be handed.

    256 bits from `secrets`, so it is neither guessable nor derivable from anything a
    caller can see — unlike a row id, which is in every admin listing.
    """
    return secrets.token_urlsafe(32)


def create_account(session: Session, email: str, password: str, role: Role) -> Account:
    """Write a new account, hashing the password on the way in.

    The plaintext is used here and nowhere else — it is never held on the returned
    ``Account``, never written to a column, and never logged.
    """
    if _find_by_email(session, email) is not None:
        raise EmailAlreadyExists(email)

    result = session.execute(
        insert(users).values(
            email=email,
            password_hash=hash_password(password),
            role=role.value,
            session_token=new_session_token(),
        )
    )
    return Account(id=int(result.inserted_primary_key[0]), email=email, role=role)


def find_by_token(session: Session, token: str) -> Account | None:
    """The account a session cookie names, or ``None``.

    This is the only lookup the session path uses. A deleted account's token matches no
    row and never will, because tokens are issued once — which is the property the row
    id could not provide.
    """
    if not token:
        return None
    row = (
        session.execute(select(users).where(users.c.session_token == token, _LIVE))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _account(row)


def session_token_for(session: Session, account_id: int) -> str | None:
    """The token to sign into a cookie for this account.

    Fetched explicitly rather than carried on ``Account``, for the same reason the
    password digest is not a field: a credential that cannot travel on the domain object
    cannot be serialised into a response by accident.
    """
    return session.execute(
        select(users.c.session_token).where(users.c.id == account_id)
    ).scalar_one_or_none()


def backfill_session_tokens(session: Session) -> int:
    """Give a token to every account that predates the column. Idempotent.

    Additive and safe on a live volume: it adds a value where there is none and touches
    nothing else. Existing sessions stop working, which is the intended cost — there is
    no logout route, so a cookie issued under the old scheme has no other way to end.
    """
    rows = session.execute(
        select(users.c.id).where(users.c.session_token.is_(None))
    ).all()
    for (account_id,) in rows:
        session.execute(
            update(users)
            .where(users.c.id == account_id)
            .values(session_token=new_session_token())
        )
    return len(rows)


def find_by_id(session: Session, account_id: int) -> Account | None:
    """The account behind a session cookie's subject, or ``None`` if it is gone."""
    row = session.execute(
        select(users).where(users.c.id == account_id, _LIVE)
    ).mappings().one_or_none()
    return None if row is None else _account(row)


def list_accounts(session: Session) -> tuple[Account, ...]:
    """Every account, ordered by id so a listing is stable between requests."""
    rows = session.execute(
        select(users).where(_LIVE).order_by(users.c.id)
    ).mappings().all()
    return tuple(_account(row) for row in rows)


def count_admins(session: Session) -> int:
    """How many admins exist. The input to the ADR-0005 guard."""
    return int(
        session.execute(
            select(func.count())
            .select_from(users)
            .where(users.c.role == Role.ADMIN.value, _LIVE)
        ).scalar_one()
    )


def set_role(session: Session, account_id: int, role: Role) -> None:
    """Change one account's role. The last-admin guard is the caller's to apply."""
    session.execute(
        update(users).where(users.c.id == account_id).values(role=role.value)
    )


def delete_account(session: Session, account_id: int) -> None:
    """Retire one account. The row stays; its id never returns to circulation.

    **Soft, and the reason is the audit trail rather than sentiment.** `audit_events`
    records `actor_account_id` and a closed rental records `account_id`. If the row were
    removed, SQLite would hand that number to the next account created, and every
    historical record naming it would silently start describing a different person —
    a departed admin's clear-flag decision attributed to their replacement. ADR-0010's
    trail is only truthful while actor identity is stable, so identity has to be
    permanent even when the account is not (ADR-0013).

    The token is cleared as well as the timestamp set. The lookups all filter on
    ``deleted_at IS NULL`` already, so this is belt: a row that cannot be matched by
    token cannot authenticate even if a future query forgets the filter.

    The last-admin guard and the open-rental guard are the caller's to apply.
    """
    session.execute(
        update(users)
        .where(users.c.id == account_id)
        .values(
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
            session_token=None,
        )
    )


def bootstrap_admin(session: Session, email: str, password: str) -> Account | None:
    """Create admin #1 from the environment if no admin exists (ADR-0005).

    Guarded by *admin* count rather than row count: a database holding only
    ``user`` accounts has reached the zero-admin state the ADR exists to prevent, and
    booting into it without an admin would leave nobody able to create one.

    Idempotent, and never overwrites. A restart must not silently reset a password
    an admin has since been using, so an existing admin is left exactly as it is —
    which also means rotating ``ADMIN_PASSWORD`` is a deliberate operation, not a
    side effect of a redeploy. Returns the account it created, or ``None``.
    """
    if count_admins(session) > 0:
        return None
    return create_account(session, email, password, Role.ADMIN)


def bootstrap_demo(session: Session, email: str, password: str) -> Account | None:
    """Create the published read-only demo account. Caller decides when.

    Deliberately **not** self-guarding on "does this account exist", because that would
    resurrect an account somebody deliberately deleted on the next restart, making the
    published credential impossible to revoke. The caller applies the emptiness guard —
    the same one the hardware seed uses — so this runs on a fresh database and never
    again.

    ``Role.USER``, never admin: `/security-review` established that a published admin
    credential on a public instance hands every reader delete rights over the inventory.
    """
    if _find_by_email(session, email) is not None:
        return None
    return create_account(session, email, password, Role.USER)


def has_no_accounts(session: Session) -> bool:
    """Whether this database has never had an account — the emptiness guard's input."""
    return (
        session.execute(select(func.count()).select_from(users)).scalar_one() == 0
    )


def _account(row) -> Account:
    """Build the domain object, deliberately dropping ``password_hash``."""
    return Account(id=row["id"], email=row["email"], role=Role(row["role"]))


def _find_by_email(session: Session, email: str) -> Account | None:
    row = session.execute(
        select(users).where(users.c.email == email)
    ).mappings().one_or_none()
    return None if row is None else _account(row)
