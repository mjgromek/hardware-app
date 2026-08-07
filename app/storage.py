"""Persistence — writing an ``IngestReport`` to SQLite and reading it back.

Thin by intent: it moves rows and makes no decisions (ADR-0002, ADR-0003). The
caller owns the transaction — the rental engine's atomic conditional UPDATE needs a
session it controls, and a module that opens an engine per call cannot give it one.
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
    # Re-exported so callers name the types they hold without importing SQLAlchemy.
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
    "edit_item",
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
    # All nullable: the seed records none of them, and the boot migration must be
    # able to ALTER them onto a live volume (see create_schema).
    Column("serial_number", String, nullable=True),
    Column("category", String, nullable=True),
    Column("date_added", Date, nullable=True),
)

#: For the boot migration — `create_all` skips a table that exists, so a live
#: volume never gets new columns from it.
_ADDED_HARDWARE_COLUMNS = (
    ("serial_number", "VARCHAR"),
    ("category", "VARCHAR"),
    ("date_added", "DATE"),
)

#: Rejected seed rows land here with a reason and the original row as evidence.
#: Synthetic key: ``source_id`` is not unique (the seed repeats id 4).
hardware_quarantine = Table(
    "hardware_quarantine",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_id", Integer, nullable=True),
    Column("reason", Text, nullable=False),
    Column("payload", Text, nullable=False),
)


def create_engine_for(database_url: str) -> Engine:
    """Build the engine, once per process.

    Default pooling and no locking pragmas, on purpose: a ``StaticPool`` hands every
    session one connection, letting one see another's uncommitted rows — the
    isolation ``test_persist_does_not_commit`` pins.
    """
    engine = create_engine(database_url)

    # SQLite leaves foreign keys unenforced unless asked, per connection (ADR-0011).
    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(connection, _record):  # pragma: no cover - driver hook
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    """Create the tables if absent, and migrate a `hardware` table that predates
    Phase 4's columns — `create_all` never adds a column to an existing table (the
    Phase 2 production defect, now a CLAUDE.md non-negotiable). Idempotent by
    inspection: `ADD COLUMN` fails on a present column. Seed id 10's `date_added`
    stays null — an honest unknown rather than an invented arrival day."""
    metadata.create_all(engine)

    with engine.begin() as connection:
        existing = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(hardware)")).all()
        }
        for column, sql_type in _ADDED_HARDWARE_COLUMNS:
            if column not in existing:
                connection.execute(
                    text(f"ALTER TABLE hardware ADD COLUMN {column} {sql_type}")
                )
        connection.execute(
            text(
                "UPDATE hardware SET date_added = purchase_date "
                "WHERE date_added IS NULL AND purchase_date IS NOT NULL"
            )
        )


def new_session(engine: Engine) -> Session:
    """Open a session the caller owns, commits, and closes."""
    return Session(engine)


def persist(report: IngestReport, session: Session) -> None:
    """Write a report through the caller's session.

    Does not commit — the caller owns the transaction boundary.

    Replace semantics, by decision: seeding twice leaves the database exactly as
    seeding once did.
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
                    "serial_number": item.serial_number,
                    "category": item.category,
                    "date_added": item.date_added or item.purchase_date,
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
                    # Evidence — stored whole, not flattened into columns it may lack.
                    "payload": json.dumps(dict(record.payload)),
                }
                for record in report.quarantined
            ],
        )


class RentalsExist(RuntimeError):
    """Raised when a reseed would truncate `hardware` under live rentals (ADR-0011)."""


def _refuse_if_rentals_exist(session: Session) -> None:
    """Refuse to replace the inventory once anybody has rented anything (ADR-0011).
    Tolerant of a database with no `rentals` table — the engine every storage test
    builds."""
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

    Filtering and ordering happen in SQL, not Python: id 10 has no purchase date,
    and a Python ``sorted`` raises ``TypeError`` on ``None`` where SQLite orders
    NULLs first and never raises.
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
            status=Status(row["status"]),
            source_id=row["source_id"],
            needs_review=bool(row["needs_review"]),
            review_reason=row["review_reason"],
            notes=row["notes"],
            history=row["history"],
            assigned_to=row["assigned_to"],
            serial_number=row["serial_number"],
            category=row["category"],
            date_added=row["date_added"],
        )
        for row in rows
    )


def add_item(
    session: Session,
    *,
    name: str,
    brand: str | None,
    purchase_date: date | None,
    serial_number: str | None = None,
    category: str | None = None,
) -> HardwareItem:
    """Insert one new item as ``Available`` and unflagged, and return it.

    The id is chosen inside the INSERT: a separate SELECT-then-insert let two
    concurrent admins read the same maximum and die on the primary key. The
    scalar subquery moves the read behind the write lock, so inserts serialise.
    Status is not caller-supplied — accepting one would let the UI create an item
    already flagged, which nobody can rent and nobody can clear (ADR-0003).
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
            serial_number=serial_number,
            category=category,
            # Dated by arrival, not purchase — the seed backfill derives from
            # `purchase_date` only because those rows have no arrival to record.
            date_added=date.today(),
        )
        .returning(hardware.c.id)
    ).scalar_one()

    return HardwareItem(
        id=assigned_id,
        name=name,
        brand=brand,
        purchase_date=purchase_date,
        status=Status.AVAILABLE,
        serial_number=serial_number,
        category=category,
        date_added=date.today(),
    )


def edit_item(session: Session, item_id: int, **fields) -> bool:
    """Change the named fields on one item. Returns whether a row matched.
    Partial semantics live at the route — the boundary that knows what was sent."""
    result = session.execute(
        update(hardware).where(hardware.c.id == item_id).values(**fields)
    )
    return result.rowcount == 1


def set_status(session: Session, item_id: int, status: Status) -> bool:
    """Move one item to ``status``. An update that matched nothing is a 404, not a
    silent success — the rowcount is the answer."""
    result = session.execute(
        update(hardware).where(hardware.c.id == item_id).values(status=status.value)
    )
    return result.rowcount == 1


def clear_review(session: Session, item_id: int) -> bool:
    """Drop the review flag and the reason together — a reason outliving its flag
    is stale prose in the column a later flag would write over."""
    result = session.execute(
        update(hardware)
        .where(hardware.c.id == item_id)
        .values(needs_review=False, review_reason=None)
    )
    return result.rowcount == 1


def flag_review(session: Session, item_id: int, reason: str) -> bool:
    """Raise the review flag with the human's reason. `review_reason` has human
    authors only — never a model's words (ADR-0014)."""
    result = session.execute(
        update(hardware)
        .where(hardware.c.id == item_id)
        .values(needs_review=True, review_reason=reason)
    )
    return result.rowcount == 1


def delete_item(session: Session, item_id: int) -> bool:
    """Remove one item — the one place the codebase deletes hardware. Quarantine is
    for seed rows; this is an admin retiring live inventory."""
    result = session.execute(delete(hardware).where(hardware.c.id == item_id))
    return result.rowcount == 1


def load_quarantine(session: Session) -> tuple[QuarantineRecord, ...]:
    """Read every quarantine record back; ``payload`` round-trips as the original row."""
    rows = session.execute(select(hardware_quarantine)).mappings().all()
    return tuple(
        QuarantineRecord(
            source_id=row["source_id"],
            reason=row["reason"],
            payload=json.loads(row["payload"]),
        )
        for row in rows
    )
