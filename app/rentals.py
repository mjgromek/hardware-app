"""The rental state machine — the transitions, and the SQL that makes them atomic.

`brainstorm.md` calls this the one load-bearing deep module of the project, and ADR-0008
settles what that means in practice: **the transition owns its own statement.** A guard
reads state and then decides, and a read followed by a write cannot win a race — two
users claiming one `Available` item both pass the same pre-check. So `rent` is a
conditional `UPDATE` whose rowcount *is* the decision, and it lives here rather than in
`app.storage` (which "makes no decisions") or `app.guards` (which cannot be atomic).

Guards still run first. They exist for the *message*: "this item is in Repair" is worth
more to a caller than a bare refusal, and ADR-0008 fixes one reason per cause. When the
pre-check passes and the `UPDATE` still matches nothing, the caller lost a race and is
told the item is in use — which by then is simply true.

**Its own `MetaData`, deliberately.** `app.storage`'s `persist` has replace semantics: it
truncates every table in *its* metadata. A `rentals` table inside that boundary would be
one refactor away from being erased by a reseed, which is the failure ADR-0011 exists to
prevent. Same reasoning as `app.accounts`.
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
    # Declared, and enforced — `create_engine_for` turns `PRAGMA foreign_keys` on.
    # ADR-0011 named this belt and it did not exist until now. `SET NULL` rather than
    # `RESTRICT` on purpose: the ADR is explicit that deleting a *returned* item stays
    # legal with its history intact, so a closed rental keeps its row and loses only the
    # pointer. An active rental cannot reach this path at all — `ensure_no_active_rental`
    # refuses that delete before the database is asked.
    Column(
        "item_id",
        Integer,
        # The column object, not the string "hardware.id": `rentals` keeps its own
        # MetaData so `persist`'s replace semantics can never reach it (ADR-0007), and a
        # string target cannot resolve across that boundary. This is why ADR-0011's belt
        # did not exist until now — declaring it needed the two decisions reconciled,
        # not just a keyword.
        ForeignKey(hardware.c.id, ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    # Nullable for exactly one reason: seed id 7 is held by an address with no account
    # behind it, and inventing an account for it would be a login-shaped hole created
    # for tidiness (ADR-0007).
    Column("account_id", Integer, nullable=True),
    # Snapshotted at rent time, so deleting an employee cannot erase the record that
    # they held the laptop — which is the one fact an audit asks for.
    Column("renter_email", String, nullable=False),
    Column("started_at", DateTime, nullable=False),
    #: ``NULL`` means active. That is the whole definition, and the partial index below
    #: is what makes "two active rentals on one item" unreachable rather than merely
    #: guarded against.
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

    ``WHERE status='Available' AND needs_review = 0`` carries the whole rule, so two
    concurrent callers cannot both match: SQLite evaluates the condition while holding
    the write lock, and the loser updates zero rows.

    The loser is told the item is `In Use`, not that it lost a race (ADR-0008). By the
    time it is told, that is the current state, and "another user claimed this
    microsecond before you" would leak implementation detail as UX.
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
    """Close your own rental. Somebody else's is a refusal, not a courtesy.

    The wrong-renter guard is absolute here on purpose (ADR-0009). An admin taking an
    item back is a different verb with a different record — see `force_return`.
    """
    rental = active_rental(session, item_id)
    if rental is None:
        raise GuardViolation(
            f"item {item_id} is not currently rented, so there is nothing to return."
        )
    # Both, and the email is the belt. `account_id` is a SQLite rowid alias, so it is
    # recyclable — the id comparison alone was enough for a newly created employee to
    # close a departed one's rental once the id came round again. The open-rental guard
    # on account deletion is what makes that unreachable; this is the second lock, and
    # it costs one comparison.
    if rental.account_id != account.id or rental.renter_email != account.email:
        raise GuardViolation(
            f"item {item_id} is held by {rental.renter_email}, not by you. An admin can "
            "recall it if it needs to come back."
        )

    return _close(session, rental, account.id, account.email, CloseKind.RETURN)


def force_return(
    session: Session, item_id: int, admin: Account, reason: str
) -> Rental:
    """An admin takes an item back from whoever holds it.

    Separate from `return_` because it is a different claim about the world: not "I am
    done with this" but "somebody decided this had to come back". The reason is
    mandatory and the caller writes an audit event (ADR-0010) — a rental that ends
    without a record of who ended it is the audit trail becoming fiction.
    """
    rental = active_rental(session, item_id)
    if rental is None:
        raise GuardViolation(
            f"item {item_id} is not currently rented, so there is nothing to recall."
        )

    return _close(session, rental, admin.id, admin.email, CloseKind.FORCE_RETURN)


def open_seed_rental(session: Session, item_id: int, renter_email: str) -> Rental | None:
    """Record the rental the seed already describes, with no account behind it.

    Seed id 7 is `In Use` and assigned to an address that has no account. ADR-0007 keeps
    it as a real rental with `account_id = NULL` rather than releasing it — releasing
    destroys the only evidence of who holds the headphones, and id 2's orphan rental was
    released precisely *because* it named nobody.

    Idempotent: a second seed run over the same item finds the active rental and leaves
    it alone, so this can sit on the boot path beside `seed_if_empty`.
    """
    if active_rental(session, item_id) is not None:
        return None
    return _insert_rental(session, item_id, None, renter_email)


def reconcile_held_items(session: Session, items) -> int:
    """Give a rental to every item that is `In Use` with a holder and no rental row.

    **Runs on every boot, not only on an empty database** — the opposite of how the seed
    is guarded, and deliberately. Seeding *writes inventory* and must never repeat;
    this *reconciles* a row that already exists.

    Found by deploying v2 over a volume Phase 1 had already seeded: `seed_if_empty`
    returns early on a populated database, so seed id 7 arrived `In Use`, held by
    `j.doe@booksy.com`, with no rental behind it. Nobody could return it, because there
    was no rental to close, and no admin could recall it for the same reason —
    `CONTEXT.md`'s "In Use with no renter" impossible state, reached through a deploy
    rather than through the seed.

    Idempotent by construction: `open_seed_rental` skips an item that already has an
    active rental, so a restart adds nothing and the partial unique index is never
    tested. Returns how many were reconciled, so boot can say if it did anything.
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
    """The items this account is holding right now.

    ``ended_at IS NULL`` is the whole definition of "right now" — without it the caller
    gets every item the employee has ever held, and My Rentals grows forever.
    """
    # `None` is not an account. SQLAlchemy renders `column == None` as `IS NULL`, which
    # would match the accountless seed rental (ADR-0007) and hand item 7 to whoever
    # asked — so the absence of an id returns nothing rather than everything nobody
    # owns. Not reachable through the API today; one line, and the alternative is a
    # data-leak-shaped bug waiting for the first caller who passes a missing id.
    if account_id is None:
        return set()

    rows = session.execute(
        select(rentals.c.item_id).where(
            rentals.c.account_id == account_id, rentals.c.ended_at.is_(None)
        )
    ).all()
    return {row[0] for row in rows}


def clear_all(session: Session) -> int:
    """Delete every rental. Only the demo reset calls this.

    Named bluntly because it is blunt: this is the data ADR-0011 stops `persist` from
    destroying. The reset uses it to *clear the blocker* before reseeding, which keeps
    the refusal intact for every other caller — a `force=True` on `persist` would have
    removed the protection for all of them.
    """
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
    """Close one rental and release the item, in the same transaction.

    A new row is never written here — the log is the rental, not an event stream, so a
    rent→return cycle is one row with both ends filled in and a second cycle is a second
    row (`docs/specs/phase-2.md`).
    """
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
