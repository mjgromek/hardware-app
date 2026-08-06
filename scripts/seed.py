"""Seed ingestion — the quarantine importer.

Ingestion validates **structure only**: schema shape, enum membership,
primary-key uniqueness, date format, and date plausibility. Semantic judgement
over free-text ``notes`` and ``history`` is explicitly outside its remit and
belongs to the Inventory Auditor (ADR-0002).

Nothing is deleted. A row that fails structural validation becomes a
``QuarantineRecord`` with a reason.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping

from app.domain import HardwareItem, IngestReport, QuarantineRecord, Status

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
      imported item carries ``needs_review`` with status ``Available``. Not
      ``Repair``: unidentifiable is not the same claim as broken, and ADR-0003's
      guard blocks the item either way.
    - **Future purchase date** — quarantined, and the item carries
      ``needs_review``.
    - **``DD-MM-YYYY`` dates** — normalised to ISO, not rejected. Parsing a date
      field is structural; correcting a value is not. ``brand: "Appel"`` is left
      exactly as the seed wrote it — that typo is the auditor's (ADR-0002).
    - **Orphan rental** (``In Use`` with no ``assignedTo``) — resolved at import.
    - **Missing optional fields** — nullable, not an error.
    """
    today = today or date.today()
    rows = [dict(record) for record in records]

    # Re-keying draws from above every id the seed uses, so a fresh id cannot
    # collide with a record that has not been reached yet.
    seed_ids = {row.get("id") for row in rows if isinstance(row.get("id"), int)}
    next_id = max(seed_ids) + 1 if seed_ids else 1

    claimed: set[int] = set()
    imported: list[HardwareItem] = []
    quarantined: list[QuarantineRecord] = []

    for row in rows:
        # One quarantine record per rejected row, however many defects it carries.
        reasons: list[str] = []
        source_id = row.get("id")

        item_id = source_id
        rekeyed_from: int | None = None
        if item_id in claimed:
            rekeyed_from = item_id
            item_id = next_id
            next_id += 1
        claimed.add(item_id)

        try:
            purchase_date = normalise_purchase_date(row.get("purchaseDate"))
        except ValueError:
            purchase_date = None
            reasons.append(
                f"purchase date {row.get('purchaseDate')!r} is not a recognised "
                "date format"
            )
        else:
            if purchase_date is not None and purchase_date > today:
                reasons.append(
                    f"purchase date {purchase_date.isoformat()} is in the future"
                )

        raw_status = row.get("status")
        try:
            status = Status(raw_status)
        except ValueError:
            # Available, never Repair: the seed tells us the record is
            # unidentifiable, not that the item is broken (ADR-0002). ADR-0003's
            # guard blocks it from rental either way.
            status = Status.AVAILABLE
            reasons.append(
                f"status {raw_status!r} is not a recognised status "
                f"({', '.join(s.value for s in Status)})"
            )

        assigned_to = row.get("assignedTo")
        if status is Status.IN_USE and not assigned_to:
            # An orphan rental names nobody to return the item, so the rental
            # cannot be reconstructed. Releasing it is the only repair available.
            status = Status.AVAILABLE

        review_reason = "; ".join(reasons) if reasons else None
        imported.append(
            HardwareItem(
                id=item_id,
                name=row.get("name", ""),
                brand=row.get("brand"),
                purchase_date=purchase_date,
                status=status,
                source_id=rekeyed_from,
                needs_review=bool(reasons),
                review_reason=review_reason,
                notes=row.get("notes"),
                history=row.get("history"),
                assigned_to=assigned_to,
            )
        )

        if reasons:
            quarantined.append(
                QuarantineRecord(
                    source_id=source_id,
                    reason=review_reason or "",
                    payload=row,
                )
            )

    return IngestReport(imported=tuple(imported), quarantined=tuple(quarantined))


def normalise_purchase_date(raw: str | None) -> date | None:
    """Parse a seed purchase date into a ``date``.

    Accepts ISO ``YYYY-MM-DD`` and the seed's stray ``DD-MM-YYYY``. Returns
    ``None`` for a null or empty value. Raises ``ValueError`` for a string that
    is neither format — structural invalidity, which is ingestion's business.
    """
    if raw is None:
        return None

    text = raw.strip()
    if not text:
        return None

    # ISO first. "22-05-2023" cannot match it — day 2023 is out of range — so the
    # two formats stay unambiguous and DD-MM-YYYY is never read month-first.
    for pattern in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue

    raise ValueError(f"{raw!r} is not a recognised purchase date format")
