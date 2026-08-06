"""Persistence — writing an ``IngestReport`` to SQLite and reading it back.

The importer stays pure: ``scripts.seed.ingest`` does structural validation in
memory and returns a report. This module is the only place that knows about a
database, which is what keeps ingestion testable without one.

Thin by intent. It moves rows in and out; it makes no decisions. Every judgement
about what a row *means* was already made upstream (ADR-0002), and every decision
about what a row *permits* belongs to the guard layer (ADR-0003).

**The caller owns the transaction.** Engine construction happens once, from
``Settings.database_url``; sessions are opened by the caller and passed in. This is
not ceremony — Phase 2's rental engine needs an atomic conditional UPDATE holding
its own connection, and a module that opens and disposes an engine per call cannot
give it one.
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    func,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.orm import Session

from app.domain import HardwareItem, IngestReport, QuarantineRecord, Status

__all__ = [
    # Re-exported so callers and tests can name the types they hold without
    # importing SQLAlchemy themselves. Types are the contract in this module.
    "Engine",
    "Session",
    "create_engine_for",
    "create_schema",
    "new_session",
    "persist",
    "load_items",
    "load_quarantine",
    "add_item",
    "RentalsExist",
    "set_status",
    "clear_review",
    "flag_review",
    "delete_item",
]

metadata = MetaData()

hardware = Table(
    "hardware",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("name", String, nullable=False),
    Column("brand", String, nullable=True),
    Column("purchase_date", Date, nullable=True),
    Column("status", String, nullable=False),
    # Set only on a re-keyed row: the id the seed originally used.
    Column("source_id", Integer, nullable=True),
    Column("needs_review", Boolean, nullable=False),
    Column("review_reason", Text, nullable=True),
    Column("notes", Text, nullable=True),
    Column("history", Text, nullable=True),
    Column("assigned_to", String, nullable=True),
)

#: Nothing from the seed is silently deleted — rejected rows land here with a
#: reason and the original row as evidence, so this table is as load-bearing as
#: ``hardware`` itself. Its own key is synthetic: ``source_id`` is not unique
#: (the seed repeats id 4) and may be absent entirely on a malformed row.
hardware_quarantine = Table(
    "hardware_quarantine",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_id", Integer, nullable=True),
    Column("reason", Text, nullable=False),
    Column("payload", Text, nullable=False),
)


def create_engine_for(database_url: str) -> Engine:
    """Build the engine for ``database_url``, e.g. ``sqlite:///./hardware_hub.db``.

    Once per process, from ``Settings.database_url`` — not once per query.

    Default pooling on purpose. A ``StaticPool`` would hand every session the same
    connection, which would let one session see another's uncommitted rows and
    quietly destroy the isolation ``test_persist_does_not_commit`` exists to pin.
    For the same reason, no locking pragmas: the onlooker's SELECT has to be able
    to run while a writer holds an open transaction.
    """
    engine = create_engine(database_url)

    # SQLite leaves foreign keys unenforced unless asked, per connection. ADR-0011
    # makes this the belt behind the two guards that actually stop rental data being
    # orphaned — it is unrelated to the locking pragmas BACKLOG.md warns against and
    # does not touch the isolation `test_persist_does_not_commit` pins.
    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(connection, _record):  # pragma: no cover - driver hook
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    """Create the hardware and quarantine tables if they are absent."""
    metadata.create_all(engine)


def new_session(engine: Engine) -> Session:
    """Open a session the caller owns, commits, and closes."""
    return Session(engine)


def persist(report: IngestReport, session: Session) -> None:
    """Write a report through the caller's session.

    Does not commit — the caller owns the transaction boundary.

    **Replace semantics, by decision.** A reseed replaces the quarantine trail
    rather than accumulating onto it: seeding twice leaves the database exactly as
    seeding once did, with no duplicated hardware items and no duplicated or lost
    quarantine records. The alternative — an audit trail that grows one copy per
    reseed — makes the table unreadable for the admin queue it exists to serve.
    A reseed is a documented operation on a deployed instance, so this behaviour
    is specified rather than incidental.
    """
    _refuse_if_rentals_exist(session)

    session.execute(delete(hardware_quarantine))
    session.execute(delete(hardware))

    if report.imported:
        session.execute(
            insert(hardware),
            [
                {
                    "id": item.id,
                    "name": item.name,
                    "brand": item.brand,
                    "purchase_date": item.purchase_date,
                    "status": item.status.value,
                    "source_id": item.source_id,
                    "needs_review": item.needs_review,
                    "review_reason": item.review_reason,
                    "notes": item.notes,
                    "history": item.history,
                    "assigned_to": item.assigned_to,
                }
                for item in report.imported
            ],
        )

    if report.quarantined:
        session.execute(
            insert(hardware_quarantine),
            [
                {
                    "source_id": record.source_id,
                    "reason": record.reason,
                    # The rejected row is evidence, so it is stored whole rather
                    # than flattened into columns it does not reliably have.
                    "payload": json.dumps(dict(record.payload)),
                }
                for record in report.quarantined
            ],
        )


class RentalsExist(RuntimeError):
    """Raised when a reseed would truncate `hardware` under live rentals (ADR-0011)."""


def _refuse_if_rentals_exist(session: Session) -> None:
    """Refuse to replace the inventory once anybody has rented anything.

    `seed_if_empty` guards the *boot* path, but the README documents
    ``railway run … python -m scripts.seed`` as a live operation and nothing guarded
    that one — so "a restart destroys every rental" was reachable through the
    documented command rather than through a bug.

    Tolerant of a database where `rentals` was never created, which is exactly the
    engine every storage test builds: an unguarded ``SELECT … FROM rentals`` would turn
    that whole module into `OperationalError`. This module still knows nothing about
    what a rental *is* — only that rows in that table mean the inventory is not
    replaceable.
    """
    if "rentals" not in inspect(session.get_bind()).get_table_names():
        return
    if session.execute(text("SELECT 1 FROM rentals LIMIT 1")).first() is None:
        return
    raise RentalsExist(
        "refusing to reseed: this database holds rental records, and replacing the "
        "inventory would destroy them. Close and remove the rentals first, or seed a "
        "fresh database."
    )


def load_items(
    session: Session,
    *,
    status: Status | None = None,
    sort_by_purchase_date: bool = False,
) -> tuple[HardwareItem, ...]:
    """Read hardware items back, optionally filtered and ordered.

    Round-trips the fields ingestion worked to establish: ``status`` as a
    ``Status`` member, ``needs_review``, ``source_id`` for re-keyed rows, and the
    normalised ``purchase_date`` as a ``date``.

    **Filtering and ordering happen in SQL, not in Python.** The reason is the one
    row the seed put there to be awkward: id 10 has no purchase date, and
    ``sorted(key=lambda item: item.purchase_date)`` raises ``TypeError`` on ``None``.
    SQLite orders NULLs first and never raises, so the undated item stays in the
    result instead of taking the endpoint down with it. Where it lands is
    deliberately not promised — see ``BACKLOG.md``.

    ``status`` is a ``Status`` member rather than a string, so an off-enum value
    cannot reach this function to be silently ignored.
    """
    query = select(hardware)
    if status is not None:
        query = query.where(hardware.c.status == status.value)
    if sort_by_purchase_date:
        query = query.order_by(hardware.c.purchase_date)

    rows = session.execute(query).mappings().all()
    return tuple(
        HardwareItem(
            id=row["id"],
            name=row["name"],
            brand=row["brand"],
            purchase_date=row["purchase_date"],
            # Back through the enum, not out as a bare string: the status stays
            # closed on the way out of the database as well as into it.
            status=Status(row["status"]),
            source_id=row["source_id"],
            needs_review=bool(row["needs_review"]),
            review_reason=row["review_reason"],
            notes=row["notes"],
            history=row["history"],
            assigned_to=row["assigned_to"],
        )
        for row in rows
    )


def add_item(
    session: Session,
    *,
    name: str,
    brand: str | None,
    purchase_date: date | None,
) -> HardwareItem:
    """Insert one new item as ``Available`` and unflagged, and return it.

    **The id is chosen by the database, inside the INSERT.** ``hardware.id`` is
    ``autoincrement=False`` because ingestion carries the seed's own ids — the seed even
    re-keyed a duplicate to 12 — so the next free id is ``max(id) + 1`` and the database
    cannot be left to invent one.

    Computing that with a separate ``SELECT`` was wrong, and concurrently wrong: two
    admins adding hardware at the same moment both read the same maximum and the second
    ``INSERT`` died on the primary key. The subquery below moves the read inside the
    write, so SQLite evaluates it while holding the write lock and the two inserts
    serialise. This is the same property Phase 2's rental engine needs from this module,
    which is why it is fixed here rather than filed.

    ``Available`` and ``needs_review=False`` are not caller-supplied. An item an admin
    is holding is in hand and not under review; accepting a status here would let the
    UI create something already flagged, which under ADR-0003 is an item nobody can
    rent and nobody can clear.
    """
    next_id = select(func.coalesce(func.max(hardware.c.id), 0) + 1).scalar_subquery()
    assigned_id = session.execute(
        insert(hardware)
        .values(
            id=next_id,
            name=name,
            brand=brand,
            purchase_date=purchase_date,
            status=Status.AVAILABLE.value,
            source_id=None,
            needs_review=False,
            review_reason=None,
            notes=None,
            history=None,
            assigned_to=None,
        )
        .returning(hardware.c.id)
    ).scalar_one()

    return HardwareItem(
        id=assigned_id,
        name=name,
        brand=brand,
        purchase_date=purchase_date,
        status=Status.AVAILABLE,
    )


def set_status(session: Session, item_id: int, status: Status) -> bool:
    """Move one item to ``status``. Returns whether a row was there to move.

    Scoped to the id in the ``WHERE`` clause, and the row count is returned rather
    than assumed — an update that matched nothing is a ``404``, not a silent success,
    and an update that matched more than the named item is the bug
    ``test_admin_can_toggle_repair_status`` looks for.
    """
    result = session.execute(
        update(hardware).where(hardware.c.id == item_id).values(status=status.value)
    )
    return result.rowcount == 1


def clear_review(session: Session, item_id: int) -> bool:
    """Drop the review flag and the reason together. Returns whether a row matched.

    Both, not just the flag: `review_reason` explains a restriction, and an item that
    is no longer restricted showing "purchase date 2027-10-10 is in the future" is
    stale prose in the column a later flag (ADR-0017) would write over.
    """
    result = session.execute(
        update(hardware)
        .where(hardware.c.id == item_id)
        .values(needs_review=False, review_reason=None)
    )
    return result.rowcount == 1


def flag_review(session: Session, item_id: int, reason: str) -> bool:
    """Raise the review flag with the human's reason. Returns whether a row matched.

    The mirror of `clear_review`, and like it a pure row-mover: whether flagging is
    allowed, who may do it and what gets audited are the route's questions (ADR-0017).
    `review_reason` has human authors only — this function is called with an admin's
    words, never a model's (ADR-0014).
    """
    result = session.execute(
        update(hardware)
        .where(hardware.c.id == item_id)
        .values(needs_review=True, review_reason=reason)
    )
    return result.rowcount == 1


def delete_item(session: Session, item_id: int) -> bool:
    """Remove one item. Returns whether it existed.

    This is the one place the codebase deletes hardware, and it is worth naming the
    difference: a seed row that fails validation is quarantined rather than dropped
    (ADR-0002), while an admin retiring a laptop is a deliberate act on live
    inventory. Only the second is a delete.
    """
    result = session.execute(delete(hardware).where(hardware.c.id == item_id))
    return result.rowcount == 1


def load_quarantine(session: Session) -> tuple[QuarantineRecord, ...]:
    """Read every quarantine record back, each carrying its readable reason.

    The reason is the whole point of the table — a row here without one is an
    unexplained deletion by another name. ``payload`` round-trips as the original
    seed row.
    """
    rows = session.execute(select(hardware_quarantine)).mappings().all()
    return tuple(
        QuarantineRecord(
            source_id=row["source_id"],
            reason=row["reason"],
            payload=json.loads(row["payload"]),
        )
        for row in rows
    )
