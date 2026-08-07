"""Seed ingestion — the quarantine importer.

Ingestion validates **structure only**: schema shape, enum membership,
primary-key uniqueness, date format, and date plausibility. Semantic judgement
over free-text ``notes`` and ``history`` is explicitly outside its remit and
belongs to the Inventory Auditor (ADR-0002).

Nothing is deleted. A row that fails structural validation becomes a
``QuarantineRecord`` with a reason.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple

from app.config import load_settings
from app.domain import HardwareItem, IngestReport, QuarantineRecord, Status
from app.storage import (
    Engine,
    create_engine_for,
    create_schema,
    load_items,
    new_session,
    persist,
)

__all__ = ["ingest", "normalise_purchase_date", "seed_if_empty", "main"]

logger = logging.getLogger(__name__)

#: The brief's 11 records, committed verbatim. Never modified — every defect in it
#: is intentional input.
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed.json"


class _Divergence(NamedTuple):
    """One way a row differs from the seed. ``needs_decision`` drives
    ``needs_review`` — an orphan rental is fully repaired at import and flagging it
    would make a usable item unrentable over paperwork; an off-enum status leaves a
    real question open, so it does both."""

    reason: str
    needs_decision: bool


def ingest(
    records: Iterable[Mapping[str, Any]],
    *,
    today: date | None = None,
) -> IngestReport:
    """Validate seed records structurally and sort them into imported vs quarantined.

    Pure: no database, no I/O. ``today`` is injected so date-plausibility checks are
    deterministic under test. The per-defect handling is specified by ADR-0002 and
    enforced line by line in docs/DATA_AUDIT.md.
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
        # One quarantine record per diverging row, however many defects it carries.
        divergences: list[_Divergence] = []
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
        except AmbiguousDate as ambiguous:
            # Two legal readings is a choice, and choices are not ingestion's
            # (ADR-0002, amended). No date stored — the weakest claim.
            purchase_date = None
            first, second = ambiguous.readings
            divergences.append(
                _Divergence(
                    f"purchase date {row.get('purchaseDate')!r} reads as "
                    f"{first.isoformat()} or {second.isoformat()}; choosing one "
                    "would be judgment, so neither was chosen",
                    needs_decision=True,
                )
            )
        except ValueError:
            purchase_date = None
            divergences.append(
                _Divergence(
                    f"purchase date {row.get('purchaseDate')!r} is not a "
                    "recognised date format",
                    needs_decision=True,
                )
            )
        else:
            if purchase_date is not None and purchase_date > today:
                divergences.append(
                    _Divergence(
                        f"purchase date {purchase_date.isoformat()} is in the "
                        "future",
                        needs_decision=True,
                    )
                )

        raw_status = row.get("status")
        try:
            status = Status(raw_status)
        except ValueError:
            # Available, never Repair: unidentifiable is not broken (ADR-0002),
            # and ADR-0003's guard blocks rental either way.
            status = Status.AVAILABLE
            divergences.append(
                _Divergence(
                    f"status {raw_status!r} is not a recognised status "
                    f"({', '.join(s.value for s in Status)})",
                    needs_decision=True,
                )
            )

        assigned_to = row.get("assignedTo")
        if status is Status.IN_USE and not assigned_to:
            # Releasing is the only repair available, and a complete one — nothing
            # is left to decide, so the item stays rentable.
            status = Status.AVAILABLE
            divergences.append(
                _Divergence(
                    "seed claimed status 'In Use' but named no assignee; the "
                    "renter could not be reconstructed, so the orphan rental was "
                    "released and the item imported as Available",
                    needs_decision=False,
                )
            )

        # The two signals, kept apart: the record holds every divergence, the
        # flag holds only those a human still has to rule on.
        undecided = [d.reason for d in divergences if d.needs_decision]
        imported.append(
            HardwareItem(
                id=item_id,
                name=row.get("name", ""),
                brand=row.get("brand"),
                purchase_date=purchase_date,
                status=status,
                source_id=rekeyed_from,
                needs_review=bool(undecided),
                review_reason="; ".join(undecided) if undecided else None,
                notes=row.get("notes"),
                history=row.get("history"),
                assigned_to=assigned_to,
            )
        )

        if divergences:
            quarantined.append(
                QuarantineRecord(
                    source_id=source_id,
                    reason="; ".join(d.reason for d in divergences),
                    payload=row,
                )
            )

    return IngestReport(imported=tuple(imported), quarantined=tuple(quarantined))


class AmbiguousDate(ValueError):
    """A date string with two legal readings, both named. A ``ValueError`` subclass
    so an uninformed caller still treats it as a bad date; ``ingest`` catches it
    first because "unrecognised" and "recognised twice" earn different reasons."""

    def __init__(self, raw: str, readings: tuple[date, date]) -> None:
        self.readings = readings
        super().__init__(
            f"{raw!r} reads as {readings[0].isoformat()} or {readings[1].isoformat()}"
        )


def normalise_purchase_date(raw: str | None) -> date | None:
    """Parse a seed purchase date that has exactly one legal reading.

    ``ValueError`` for a string matching neither format; ``AmbiguousDate`` where the
    day/month transposition is also legal and lands on a different day — choosing
    would be the same guess about intent ADR-0002 refuses over ``"Appel"``. (The
    first version chose day-first silently; caught by a self-grilling, not the suite.)
    """
    if raw is None:
        return None

    text = raw.strip()
    if not text:
        return None

    # ISO first, and ISO is never ambiguous: the standard fixes the field order.
    # "22-05-2023" cannot match it — day 2023 is out of range.
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass

    try:
        parsed = datetime.strptime(text, "%d-%m-%Y").date()
    except ValueError:
        raise ValueError(f"{raw!r} is not a recognised purchase date format")

    # One legal reading, or none at all. The transposition is ambiguous only when
    # it is itself a real date (day fits a month slot) *and* differs — 04-04 reads
    # the same both ways, so nothing is being chosen.
    if parsed.day <= 12 and parsed.day != parsed.month:
        transposed = date(parsed.year, parsed.day, parsed.month)
        return_first, return_second = sorted((parsed, transposed))
        raise AmbiguousDate(raw, (return_first, return_second))

    return parsed


def main() -> None:
    """Ingest ``data/seed.json`` into the configured database: ``python -m scripts.seed``."""
    settings = load_settings(os.environ)
    report = ingest(json.loads(SEED_PATH.read_text(encoding="utf-8")))

    engine = create_engine_for(settings.database_url)
    create_schema(engine)
    _create_rentals_schema(engine)
    with new_session(engine) as session:
        persist(report, session)
        _open_seed_rentals(report, session)
        session.commit()

    print(
        f"seeded {len(report.imported)} hardware items, "
        f"{len(report.quarantined)} quarantine records -> {settings.database_url}"
    )


def _create_rentals_schema(engine: Engine) -> None:
    """DDL before the session, never inside it.

    SQLite will not run `CREATE TABLE` on a second connection while another holds a
    write transaction — the fixture that seeds and then opens rentals in one session
    deadlocks itself otherwise.
    """
    from app.rentals import create_schema as create_rentals_schema

    create_rentals_schema(engine)


def _open_seed_rentals(report: IngestReport, session) -> int:
    """Record the rentals the seed already describes, above `persist` — deliberately:
    `persist` refuses once rentals exist and must succeed twice on a fresh database,
    which both hold only if it never writes a rental itself (ADR-0007, ADR-0011)."""
    from app.rentals import reconcile_held_items

    return reconcile_held_items(session, report.imported)


def seed_if_empty(engine: Engine) -> bool:
    """Seed the database only if it holds no hardware items. Returns whether it did.

    A deploy shim, not a migration strategy (BACKLOG.md). The emptiness check is
    the safety: `persist` has replace semantics, so an unguarded boot seed would
    wipe the table — and every rental — on every restart. Never remove the guard.
    """
    with new_session(engine) as session:
        existing = load_items(session)
        if existing:
            logger.info(
                "boot seed skipped: %d hardware items already present", len(existing)
            )
            return False

        report = ingest(json.loads(SEED_PATH.read_text(encoding="utf-8")))
        persist(report, session)
        _open_seed_rentals(report, session)
        session.commit()

    logger.info(
        "boot seed ran on an empty database: seeded %d hardware items, "
        "%d quarantine records",
        len(report.imported),
        len(report.quarantined),
    )
    return True


# Last in the file, deliberately: this block once sat above two helpers `main()`
# reaches — imports bound them and every test passed, while the README's own setup
# step died on a NameError. Found by a fresh-clone check, not by the suite.
if __name__ == "__main__":
    main()
