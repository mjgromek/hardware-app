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


@dataclass(frozen=True)
class HardwareItem:
    """A single piece of company equipment.

    ``source_id`` preserves the original seed ``id`` when a record had to be
    re-keyed. ``needs_review`` is a rentability guard, not a badge (ADR-0003).
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
