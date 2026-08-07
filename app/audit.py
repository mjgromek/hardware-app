"""`audit_events` — one table for every admin override, with a reason attached (ADR-0010).

Ordinary rent and return write nothing here; the `rentals` row is their record.
Kept out of `hardware_quarantine` because `persist` has replace semantics — an audit
trail there survives only until the next reseed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    ForeignKey,
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
from app.storage import hardware

__all__ = ["Action", "create_schema", "record", "clear_all"]

metadata = MetaData()


class Action:
    """A closed set — a trail whose vocabulary drifts cannot be queried."""

    FORCE_RETURN = "force_return"
    CLEAR_REVIEW_FLAG = "clear_review_flag"
    FLAG_REVIEW = "flag_review"
    #: Not a `clear_review_flag` with fault-shaped prose: a trail that cannot tell
    #: "released as fit" from "confirmed unfit" cannot answer an incident (ADR-0017).
    REVIEW_TO_REPAIR = "review_to_repair"
    #: Its own action because the actor class is the point — this flag rests on
    #: direct observation, and the admin's next move is to ask the returner (ADR-0020).
    REPORT_ON_RETURN = "report_on_return"

    ALL = (
        FORCE_RETURN,
        CLEAR_REVIEW_FLAG,
        FLAG_REVIEW,
        REVIEW_TO_REPAIR,
        REPORT_ON_RETURN,
    )


audit_events = Table(
    "audit_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # Actor stored twice: deleting an admin must not erase what they did (ADR-0007).
    Column("actor_account_id", Integer, nullable=True),
    Column("actor_email", String, nullable=False),
    Column("action", String, nullable=False),
    # SET NULL: the event outlives the item it describes.
    Column("item_id", Integer, ForeignKey(hardware.c.id, ondelete="SET NULL"), nullable=True),
    Column("rental_id", Integer, nullable=True),
    # Mandatory — a cleared flag with no reason is indefensible (ADR-0010).
    Column("reason", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


def create_schema(engine: Engine) -> None:
    """Create the audit table if it is absent."""
    metadata.create_all(engine)


def clear_all(session: Session) -> int:
    """Delete every audit event. Only the demo reset calls this — a reseed that kept
    the events would leave a trail whose ids no longer mean what it says."""
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
