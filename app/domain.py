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
    """Exactly two. A role only changes because an admin changed it (ADR-0005)."""

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
    """Closed for the reason `Status` is: an off-enum value makes an item invisible
    rather than wrong, which is worse."""

    LAPTOP = "Laptop"
    MOBILE = "Mobile"
    TABLET = "Tablet"
    MONITOR = "Monitor"
    ACCESSORY = "Accessory"


@dataclass(frozen=True)
class HardwareItem:
    """A single piece of company equipment. ``source_id`` preserves a re-keyed seed
    id; ``needs_review`` is a rentability guard, not a badge (ADR-0003)."""

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
    """A seed row that diverged, kept with a reason — nothing disappears silently."""

    source_id: int | None
    reason: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class IngestReport:
    """The outcome of one ingestion run over a set of seed records."""

    imported: tuple[HardwareItem, ...] = field(default_factory=tuple)
    quarantined: tuple[QuarantineRecord, ...] = field(default_factory=tuple)


#: Serialised for admins only (ADR-0012). Renter identity is deliberately not here.
ADMIN_ONLY_FIELDS = ("notes", "history", "review_reason")


def visible_to(item: dict[str, Any], account: Account) -> dict[str, Any]:
    """One item, as this caller is allowed to see it (ADR-0012).

    Restricted fields are set to `None` rather than dropped, so the payload keeps
    one shape and the client never branches on role.
    """
    if account.role is Role.ADMIN:
        return item
    return {
        key: (None if key in ADMIN_ONLY_FIELDS else value) for key, value in item.items()
    }
