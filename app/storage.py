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
    insert,
    select,
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
    return create_engine(database_url)


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


def load_items(session: Session) -> tuple[HardwareItem, ...]:
    """Read every hardware item back.

    Round-trips the fields ingestion worked to establish: ``status`` as a
    ``Status`` member, ``needs_review``, ``source_id`` for re-keyed rows, and the
    normalised ``purchase_date`` as a ``date``.
    """
    rows = session.execute(select(hardware)).mappings().all()
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
