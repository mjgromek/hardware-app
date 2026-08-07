"""The rental state machine — the transitions, and the SQL that makes them atomic.

A read followed by a write cannot win a race, so the conditional `UPDATE` in `rent`
is the decision and its rowcount is the answer (ADR-0008); guards run first only for
the message. Its own `MetaData`, deliberately: `persist` truncates every table in
*its* metadata, and a rentals table inside that boundary would be one refactor away
from being erased by a reseed (ADR-0011).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.orm import Session

from app import audit
from app.domain import Account, Status
from app.guards import GuardViolation
from app.storage import hardware

__all__ = [
    "Rental",
    "create_schema",
    "rent",
    "return_",
    "force_return",
    "open_seed_rental",
    "reconcile_held_items",
    "active_rental",
    "item_ids_held_by",
    "rental_count",
    "clear_all",
    "CloseKind",
]

metadata = MetaData()

rentals = Table(
    "rentals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # SET NULL, not RESTRICT: deleting a *returned* item stays legal with its history
    # intact (ADR-0011); an active rental never reaches this path. The column object,
    # not the string "hardware.id" — a string target cannot resolve across the
    # separate-MetaData boundary.
    Column(
        "item_id",
        Integer,
        ForeignKey(hardware.c.id, ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    # Nullable for exactly one row: seed id 7's holder has no account, and inventing
    # one would be a login-shaped hole created for tidiness (ADR-0007).
    Column("account_id", Integer, nullable=True),
    # Snapshotted at rent time — deleting an employee must not erase who held the laptop.
    Column("renter_email", String, nullable=False),
    Column("started_at", DateTime, nullable=False),
    #: NULL means active; the partial index below makes "two active rentals on one
    #: item" unreachable rather than guarded against.
    Column("ended_at", DateTime, nullable=True),
    Column("closed_by_account_id", Integer, nullable=True),
    Column("closed_by_email", String, nullable=True),
    Column("close_kind", Text, nullable=True),
)

Index(
    "ix_rentals_one_active_per_item",
    rentals.c.item_id,
    unique=True,
    sqlite_where=rentals.c.ended_at.is_(None),
)


class CloseKind:
    """How a rental ended. `close_kind` exists so `My Rentals` can say which."""

    RETURN = "return"
    FORCE_RETURN = "force_return"


@dataclass(frozen=True)
class Rental:
    """One rent→return cycle. An active rental has no `ended_at` (CONTEXT.md)."""

    id: int
    item_id: int
    account_id: int | None
    renter_email: str
    started_at: datetime
    ended_at: datetime | None = None


def create_schema(engine: Engine) -> None:
    """Create the rentals table and its partial unique index if absent."""
    metadata.create_all(engine)


def rent(session: Session, item_id: int, account: Account) -> Rental:
    """Claim an item. The `UPDATE` is the claim; its rowcount is the answer.

    The WHERE clause carries the whole rule — SQLite evaluates it holding the write
    lock, so the loser updates zero rows and is told the item is In Use, which by
    then is simply true (ADR-0008).
    """
    claimed = session.execute(
        update(hardware)
        .where(
            hardware.c.id == item_id,
            hardware.c.status == Status.AVAILABLE.value,
            hardware.c.needs_review == False,  # noqa: E712 — SQL, not Python truthiness
        )
        .values(status=Status.IN_USE.value, assigned_to=account.email)
    ).rowcount

    if claimed != 1:
        raise GuardViolation(
            f"item {item_id} is already in use — somebody else has it. Ask them, or "
            "wait until it is returned."
        )

    return _insert_rental(session, item_id, account.id, account.email)


def return_(session: Session, item_id: int, account: Account) -> Rental:
    """Close your own rental. Somebody else's is a refusal, not a courtesy (ADR-0009)."""
    rental = active_rental(session, item_id)
    if rental is None:
        raise GuardViolation(
            f"item {item_id} is not currently rented, so there is nothing to return."
        )
    # The email is the belt: `account_id` is a recyclable rowid, and the id
    # comparison alone once let a new employee close a departed one's rental.
    if rental.account_id != account.id or rental.renter_email != account.email:
        raise GuardViolation(
            f"item {item_id} is held by {rental.renter_email}, not by you. An admin can "
            "recall it if it needs to come back."
        )

    return _close(session, rental, account.id, account.email, CloseKind.RETURN)


def force_return(
    session: Session, item_id: int, admin: Account, reason: str
) -> Rental:
    """An admin takes an item back. *This function* writes the audit event, in the
    same transaction as the close — trusting the caller to meant any second caller
    could end a rental and leave no record (ADR-0010)."""
    rental = active_rental(session, item_id)
    if rental is None:
        raise GuardViolation(
            f"item {item_id} is not currently rented, so there is nothing to recall."
        )

    closed = _close(session, rental, admin.id, admin.email, CloseKind.FORCE_RETURN)
    audit.record(
        session,
        actor=admin,
        action=audit.Action.FORCE_RETURN,
        reason=reason,
        item_id=item_id,
        rental_id=closed.id,
    )
    return closed


def open_seed_rental(session: Session, item_id: int, renter_email: str) -> Rental | None:
    """Record the rental the seed already describes, `account_id = NULL` (ADR-0007).
    Idempotent, so it can sit on the boot path."""
    if active_rental(session, item_id) is not None:
        return None
    return _insert_rental(session, item_id, None, renter_email)


def reconcile_held_items(session: Session, items) -> int:
    """Give a rental to every item that is `In Use` with a holder and no rental row.

    Runs on every boot, unlike the seed — seeding *writes inventory* and must never
    repeat; this *reconciles* a row that already exists. Born of a production defect:
    a volume seeded before the rentals table existed held an item nobody could return
    (AI_LOG Correction #4). Idempotent via `open_seed_rental`'s skip.
    """
    reconciled = 0
    for item in items:
        if item.status is Status.IN_USE and item.assigned_to:
            if open_seed_rental(session, item.id, item.assigned_to) is not None:
                reconciled += 1
    return reconciled


def active_rental(session: Session, item_id: int) -> Rental | None:
    """The open rental on this item, or `None`. `ended_at IS NULL` is the definition."""
    row = (
        session.execute(
            select(rentals).where(
                rentals.c.item_id == item_id, rentals.c.ended_at.is_(None)
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _rental(row)


def item_ids_held_by(session: Session, account_id: int) -> set[int]:
    """The items this account is holding right now."""
    # `None` is not an account: SQLAlchemy renders `== None` as `IS NULL`, which
    # would hand the accountless seed rental (ADR-0007) to whoever asked.
    if account_id is None:
        return set()

    rows = session.execute(
        select(rentals.c.item_id).where(
            rentals.c.account_id == account_id, rentals.c.ended_at.is_(None)
        )
    ).all()
    return {row[0] for row in rows}


def clear_all(session: Session) -> int:
    """Delete every rental. Only the demo reset calls this — it clears the blocker
    ADR-0011 puts in front of `persist`, keeping the refusal intact for everyone else."""
    result = session.execute(delete(rentals))
    return result.rowcount


def rental_count(session: Session) -> int:
    """How many rentals exist at all, open or closed. Input to ADR-0011's refusal."""
    return len(session.execute(select(rentals.c.id)).all())


def _insert_rental(
    session: Session, item_id: int, account_id: int | None, renter_email: str
) -> Rental:
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    new_id = session.execute(
        insert(rentals)
        .values(
            item_id=item_id,
            account_id=account_id,
            renter_email=renter_email,
            started_at=started_at,
        )
        .returning(rentals.c.id)
    ).scalar_one()
    return Rental(
        id=int(new_id),
        item_id=item_id,
        account_id=account_id,
        renter_email=renter_email,
        started_at=started_at,
    )


def _close(
    session: Session,
    rental: Rental,
    closed_by_account_id: int | None,
    closed_by_email: str,
    close_kind: str,
) -> Rental:
    """Close one rental and release the item, in the same transaction. The log is
    the rental, not an event stream: one cycle, one row, both ends filled in."""
    ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.execute(
        update(rentals)
        .where(rentals.c.id == rental.id)
        .values(
            ended_at=ended_at,
            closed_by_account_id=closed_by_account_id,
            closed_by_email=closed_by_email,
            close_kind=close_kind,
        )
    )
    session.execute(
        update(hardware)
        .where(hardware.c.id == rental.item_id)
        .values(status=Status.AVAILABLE.value, assigned_to=None)
    )
    return Rental(
        id=rental.id,
        item_id=rental.item_id,
        account_id=rental.account_id,
        renter_email=rental.renter_email,
        started_at=rental.started_at,
        ended_at=ended_at,
    )


def _rental(row) -> Rental:
    return Rental(
        id=row["id"],
        item_id=row["item_id"],
        account_id=row["account_id"],
        renter_email=row["renter_email"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )
