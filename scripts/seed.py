"""Seed ingestion — the quarantine importer.

Ingestion validates **structure only**: schema shape, enum membership,
primary-key uniqueness, date format, and date plausibility. Semantic judgement
over free-text ``notes`` and ``history`` is explicitly outside its remit and
belongs to the Inventory Auditor (ADR-0002).

Nothing is deleted. A row that fails structural validation becomes a
``QuarantineRecord`` with a reason.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

from app.domain import IngestReport

__all__ = ["ingest", "normalise_purchase_date"]


def ingest(
    records: Iterable[Mapping[str, Any]],
    *,
    today: date | None = None,
) -> IngestReport:
    """Validate seed records structurally and sort them into imported vs quarantined.

    Pure: no database, no I/O. ``today`` is injected so that plausibility checks
    over purchase dates are deterministic under test.

    Expected structural handling, per `brainstorm.md` §2:

    - **Duplicate primary key** — the second occurrence is re-keyed to a fresh
      id, with the original preserved as ``source_id``. Neither row is dropped.
    - **Off-enum status** (the seed's ``"Unknown"``) — quarantined, and the
      imported item carries ``needs_review``.
    - **Future purchase date** — quarantined, and the item carries
      ``needs_review``.
    - **``DD-MM-YYYY`` dates** — normalised to ISO, not rejected.
    - **Orphan rental** (``In Use`` with no ``assignedTo``) — resolved at import.
    - **Missing optional fields** — nullable, not an error.
    """
    raise NotImplementedError("ingest is not implemented yet")


def normalise_purchase_date(raw: str | None) -> date | None:
    """Parse a seed purchase date into a ``date``.

    Accepts ISO ``YYYY-MM-DD`` and the seed's stray ``DD-MM-YYYY``. Returns
    ``None`` for a null or empty value. Raises ``ValueError`` for a string that
    is neither format — structural invalidity, which is ingestion's business.
    """
    raise NotImplementedError("normalise_purchase_date is not implemented yet")
