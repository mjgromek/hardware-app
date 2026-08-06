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

from sqlalchemy import (
    Column,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    select,
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
)

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


def create_schema(engine: Engine) -> None:
    """Create the users table if it is absent."""
    metadata.create_all(engine)


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
        select(users).where(users.c.email == email)
    ).mappings().one_or_none()

    if row is None:
        _matches(password, _ABSENT_ACCOUNT_HASH)
        return None
    if not _matches(password, row["password_hash"]):
        return None
    return _account(row)


def create_account(session: Session, email: str, password: str, role: Role) -> Account:
    """Write a new account, hashing the password on the way in.

    The plaintext is used here and nowhere else — it is never held on the returned
    ``Account``, never written to a column, and never logged.
    """
    if _find_by_email(session, email) is not None:
        raise EmailAlreadyExists(email)

    result = session.execute(
        insert(users).values(
            email=email, password_hash=hash_password(password), role=role.value
        )
    )
    return Account(id=int(result.inserted_primary_key[0]), email=email, role=role)


def find_by_id(session: Session, account_id: int) -> Account | None:
    """The account behind a session cookie's subject, or ``None`` if it is gone."""
    row = session.execute(
        select(users).where(users.c.id == account_id)
    ).mappings().one_or_none()
    return None if row is None else _account(row)


def list_accounts(session: Session) -> tuple[Account, ...]:
    """Every account, ordered by id so a listing is stable between requests."""
    rows = session.execute(
        select(users).order_by(users.c.id)
    ).mappings().all()
    return tuple(_account(row) for row in rows)


def count_admins(session: Session) -> int:
    """How many admins exist. The input to the ADR-0005 guard."""
    return int(
        session.execute(
            select(func.count()).select_from(users).where(users.c.role == Role.ADMIN.value)
        ).scalar_one()
    )


def set_role(session: Session, account_id: int, role: Role) -> None:
    """Change one account's role. The last-admin guard is the caller's to apply."""
    session.execute(
        update(users).where(users.c.id == account_id).values(role=role.value)
    )


def delete_account(session: Session, account_id: int) -> None:
    """Remove one account. The last-admin guard is the caller's to apply."""
    session.execute(delete(users).where(users.c.id == account_id))


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
