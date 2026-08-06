"""`audit_events` — one table for every admin override, with a reason attached.

ADR-0010: force-returning somebody else's rental and clearing `needs_review` are the
same *kind* of event — an admin doing something an ordinary user could not — so they
share one table rather than getting one each. Two tables for one concept is the
shallow-module shape `architecture-scout` is briefed to flag.

**Ordinary rent and return write nothing here.** A user renting a laptop is the product
working, and the `rentals` row is its record. This table is for the overrides.

`hardware_quarantine` was the obvious place and is the wrong one: `persist` has replace
semantics, so an audit trail there survives only until the next documented reseed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
)
from sqlalchemy.orm import Session

from app.domain import Account

__all__ = ["Action", "create_schema", "record", "clear_all"]

metadata = MetaData()


class Action:
    """What an admin did. A closed set, for the reason `Status` and `SortKey` are.

    An unrecognised action must not be silently storable — an audit trail whose
    vocabulary drifts cannot be queried, and the first question anyone asks it is "show
    me every X".
    """

    FORCE_RETURN = "force_return"
    CLEAR_REVIEW_FLAG = "clear_review_flag"

    ALL = (FORCE_RETURN, CLEAR_REVIEW_FLAG)


audit_events = Table(
    "audit_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # The actor is stored twice for the same reason the renter is (ADR-0007): deleting
    # an admin must not erase the record of what they did.
    Column("actor_account_id", Integer, nullable=True),
    Column("actor_email", String, nullable=False),
    Column("action", String, nullable=False),
    Column("item_id", Integer, nullable=True),
    Column("rental_id", Integer, nullable=True),
    #: Mandatory. "Somebody inspected this and it is fit to issue" is the claim a later
    #: incident interrogates, and a cleared flag with no reason is indefensible on the
    #: one item — the Dell XPS — where it matters most.
    Column("reason", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


def create_schema(engine: Engine) -> None:
    """Create the audit table if it is absent."""
    metadata.create_all(engine)


def clear_all(session: Session) -> int:
    """Delete every audit event. Only the demo reset calls this.

    A reset that reseeded the inventory but kept the events would leave a trail
    referencing item and rental ids that no longer mean what it says.
    """
    return session.execute(delete(audit_events)).rowcount


def record(
    session: Session,
    *,
    actor: Account,
    action: str,
    reason: str,
    item_id: int | None = None,
    rental_id: int | None = None,
) -> None:
    """Write one audit event. Rejects an action outside the closed set."""
    if action not in Action.ALL:
        raise ValueError(f"unknown audit action {action!r}")

    session.execute(
        insert(audit_events).values(
            actor_account_id=actor.id,
            actor_email=actor.email,
            action=action,
            item_id=item_id,
            rental_id=rental_id,
            reason=reason,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
