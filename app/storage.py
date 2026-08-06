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

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.domain import HardwareItem, IngestReport, QuarantineRecord

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


def create_engine_for(database_url: str) -> Engine:
    """Build the engine for ``database_url``, e.g. ``sqlite:///./hardware_hub.db``.

    Once per process, from ``Settings.database_url`` — not once per query.
    """
    raise NotImplementedError("create_engine_for is not implemented yet")


def create_schema(engine: Engine) -> None:
    """Create the hardware and quarantine tables if they are absent."""
    raise NotImplementedError("create_schema is not implemented yet")


def new_session(engine: Engine) -> Session:
    """Open a session the caller owns, commits, and closes."""
    raise NotImplementedError("new_session is not implemented yet")


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
    raise NotImplementedError("persist is not implemented yet")


def load_items(session: Session) -> tuple[HardwareItem, ...]:
    """Read every hardware item back.

    Round-trips the fields ingestion worked to establish: ``status`` as a
    ``Status`` member, ``needs_review``, ``source_id`` for re-keyed rows, and the
    normalised ``purchase_date`` as a ``date``.
    """
    raise NotImplementedError("load_items is not implemented yet")


def load_quarantine(session: Session) -> tuple[QuarantineRecord, ...]:
    """Read every quarantine record back, each carrying its readable reason.

    The reason is the whole point of the table — a row here without one is an
    unexplained deletion by another name. ``payload`` round-trips as the original
    seed row.
    """
    raise NotImplementedError("load_quarantine is not implemented yet")
