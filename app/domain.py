"""The vocabulary from CONTEXT.md, as types.

Structure only. Every behaviour lives in the modules that consume these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Mapping


class Status(str, Enum):
    """Exactly three values. ``"Unknown"`` is not one of them — see ``needs_review``."""

    AVAILABLE = "Available"
    IN_USE = "In Use"
    REPAIR = "Repair"


class Role(str, Enum):
    """What an account may do. Exactly two, and the difference is authorization.

    ``ADMIN`` manages hardware and accounts; ``USER`` rents. There is no
    self-registration and no self-promotion, so a role only ever changes because an
    admin changed it — and never to a state with no admins left (ADR-0005).
    """

    ADMIN = "admin"
    USER = "user"


@dataclass(frozen=True)
class Account:
    """An employee who can sign in.

    **The password hash is deliberately not a field.** Callers get an ``Account``
    only after ``app.accounts`` has already verified a credential, so the digest has
    no reason to travel: a type that cannot carry it cannot leak it into a response
    body, a log line or a template.
    """

    id: int
    email: str
    role: Role


class Category(str, Enum):
    """The closed set of device categories (brainstorm §3 Phase 4).

    Closed for the reason `Status` is: a sixth value is not a new option, it is a
    bug — a category no screen renders and no filter matches makes the item
    invisible rather than wrong, which is worse.
    """

    LAPTOP = "Laptop"
    MOBILE = "Mobile"
    TABLET = "Tablet"
    MONITOR = "Monitor"
    ACCESSORY = "Accessory"


@dataclass(frozen=True)
class HardwareItem:
    """A single piece of company equipment.

    ``source_id`` preserves the original seed ``id`` when a record had to be
    re-keyed. ``needs_review`` is a rentability guard, not a badge (ADR-0003).
    The Phase 4 trio — ``serial_number``, ``category``, ``date_added`` — are all
    nullable because the seed's eleven records carry none of them.
    """

    id: int
    name: str
    brand: str | None
    purchase_date: date | None
    status: Status
    source_id: int | None = None
    needs_review: bool = False
    review_reason: str | None = None
    notes: str | None = None
    history: str | None = None
    assigned_to: str | None = None
    serial_number: str | None = None
    category: str | None = None
    date_added: date | None = None


@dataclass(frozen=True)
class QuarantineRecord:
    """A seed row that failed structural validation.

    Written to ``hardware_quarantine`` with a reason rather than dropped.
    Ingestion is loss-free by design: nothing disappears silently.
    """

    source_id: int | None
    reason: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class IngestReport:
    """The outcome of one ingestion run over a set of seed records."""

    imported: tuple[HardwareItem, ...] = field(default_factory=tuple)
    quarantined: tuple[QuarantineRecord, ...] = field(default_factory=tuple)


#: Serialised for admins only (ADR-0012). Maintenance prose written for an auditor to
#: read — the Phase 3 auditor consumes these columns and never writes them (ADR-0014).
#: Renter identity is *not* here: who holds a laptop is operational, and hiding it
#: moves the question to Slack.
ADMIN_ONLY_FIELDS = ("notes", "history", "review_reason")


def visible_to(item: dict[str, Any], account: Account) -> dict[str, Any]:
    """One item, as this caller is allowed to see it.

    Lives here rather than in the routes module because ADR-0012's rule has three
    callers in Phase 3 — the item list, semantic search, and the auditor — and a rule
    every caller must import from `app.main` is a dependency pointing the wrong way
    (`architecture-scout`, filed at the Phase 2 gate).

    The restricted fields are set to `None` rather than dropped, so the payload keeps
    one shape and the client does not have to branch on which role it is.
    """
    if account.role is Role.ADMIN:
        return item
    return {
        key: (None if key in ADMIN_ONLY_FIELDS else value) for key, value in item.items()
    }
