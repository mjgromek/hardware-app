"""Accounts — who exists, and whether a submitted password belongs to them.

The password digest never leaves this module. The table lives here rather than in
``app.storage`` because storage has replace semantics — an account table inside that
boundary would be one refactor away from being wiped by a reseed.
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
    Column("email", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("role", String, nullable=False),
    #: What a session cookie names — never the row id, which SQLite recycles
    #: (ADR-0013). Nullable only so it can be added to a live database and backfilled.
    Column("session_token", String, nullable=True, unique=True),
    #: The row is never deleted — that is what keeps its id out of circulation, and
    #: the audit trail truthful (ADR-0013).
    Column("deleted_at", DateTime, nullable=True),
)

#: Every authentication and listing read carries this filter.
_LIVE = users.c.deleted_at.is_(None)

#: scrypt cost: ~16 MB, ~50 ms — slow for a stolen database file, invisible at login.
#: Stored per-hash, so raising it later does not invalidate existing rows.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1

_FORMAT = "scrypt${n}${r}${p}${salt}${digest}"


class EmailAlreadyExists(ValueError):
    """Raised when an account already holds the requested address."""


#: SQLite refuses `ADD COLUMN` with a UNIQUE constraint, so `session_token`'s
#: uniqueness is a separate index that both paths (fresh and migrated) end up with.
_ADDED_COLUMNS = (
    ("session_token", "VARCHAR"),
    ("deleted_at", "DATETIME"),
)


def create_schema(engine: Engine) -> None:
    """Create the users table if absent, and bring an older one up to date.

    The second half exists because `create_all` skips an existing table, columns and
    all — a live volume never received ADR-0013's columns and served 502s (AI_LOG
    Correction #4). Idempotent by inspection: `ADD COLUMN` fails on a present column.
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
    """A salted scrypt digest — fresh 16-byte salt per call, so one precomputed
    table cannot answer for two accounts sharing a password."""
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
    """Constant-time match. A malformed stored value is a mismatch, not an
    exception — one corrupt row should refuse one login, not 500 the endpoint."""
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = _derive(password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, actual)


#: Burned when an email has no account, so "no such account" costs the same as
#: "wrong password" — otherwise timing enumerates accounts through the side channel
#: the identical response bodies close.
_ABSENT_ACCOUNT_HASH = hash_password("no account holds this address")


def verify_credentials(session: Session, email: str, password: str) -> Account | None:
    """The account these credentials belong to, or ``None`` — one function for the
    whole question, so no caller can answer "does this email exist" out loud."""
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
    """A session identity no future account can be handed — issued once, never reissued."""
    return secrets.token_urlsafe(32)


def create_account(session: Session, email: str, password: str, role: Role) -> Account:
    """Write a new account, hashing the password on the way in."""
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
    """The account a session cookie names, or ``None``."""
    if not token:
        return None
    row = (
        session.execute(select(users).where(users.c.session_token == token, _LIVE))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _account(row)


def session_token_for(session: Session, account_id: int) -> str | None:
    """Fetched explicitly rather than carried on ``Account`` — a credential that
    cannot travel on the domain object cannot be serialised by accident."""
    return session.execute(
        select(users.c.session_token).where(users.c.id == account_id)
    ).scalar_one_or_none()


def backfill_session_tokens(session: Session) -> int:
    """Give a token to every account that predates the column. Idempotent."""
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
    """Retire one account. Soft, so its id never returns to circulation and the
    audit trail stays truthful (ADR-0013). The token is cleared as belt: a row that
    matches no token cannot authenticate even if a query forgets the ``_LIVE``
    filter. Guards are the caller's to apply."""
    session.execute(
        update(users)
        .where(users.c.id == account_id)
        .values(
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
            session_token=None,
        )
    )


def bootstrap_admin(session: Session, email: str, password: str) -> Account | None:
    """Create admin #1 if no admin exists (ADR-0005). Never overwrites — a restart
    must not silently reset a password an admin has since been using."""
    if count_admins(session) > 0:
        return None
    return create_account(session, email, password, Role.ADMIN)


def bootstrap_demo(session: Session, email: str, password: str) -> Account | None:
    """Create the published demo account. Deliberately not self-guarding on
    existence — that would resurrect a deliberately deleted account every restart,
    making the published credential impossible to revoke. ``Role.USER``, never admin."""
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
