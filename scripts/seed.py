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
    """One way an imported row differs from the seed, and who has to act on it.

    Recording a divergence and blocking rental are separate questions, and
    collapsing them is a mistake: an orphan rental is *fully repaired* at import,
    so it belongs in the audit trail but leaves nothing for a human to rule on.
    An off-enum status leaves a real question open, so it does both.

    ``needs_decision`` is what drives ``needs_review``, which under ADR-0003 is a
    rentability guard. Flagging a repaired row would make a usable item
    unrentable over paperwork.
    """

    reason: str
    needs_decision: bool


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
            # (ADR-0002, amended). No date is stored — the weakest claim — and
            # the reason names both candidates so the ruling human does not
            # re-derive them.
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
            # Available, never Repair: the seed tells us the record is
            # unidentifiable, not that the item is broken (ADR-0002). ADR-0003's
            # guard blocks it from rental either way.
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
            # An orphan rental names nobody to return the item, so the rental
            # cannot be reconstructed. Releasing it is the only repair available
            # — and it is a complete repair, which is why nothing is left to
            # decide and the item stays rentable.
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
    """A date string with two legal readings, both named.

    A subclass of ``ValueError`` so an uninformed caller still treats it as a bad
    date — but ``ingest`` catches it first and quarantines with both readings,
    because "unrecognised" and "recognised twice" earn different reasons.
    """

    def __init__(self, raw: str, readings: tuple[date, date]) -> None:
        self.readings = readings
        super().__init__(
            f"{raw!r} reads as {readings[0].isoformat()} or {readings[1].isoformat()}"
        )


def normalise_purchase_date(raw: str | None) -> date | None:
    """Parse a seed purchase date that has exactly one legal reading.

    Accepts ISO ``YYYY-MM-DD`` and the seed's stray day-first ``DD-MM-YYYY``.
    Returns ``None`` for a null or empty value. Raises ``ValueError`` for a
    string matching neither format, and ``AmbiguousDate`` for one matching the
    day-first pattern where the month-first transposition is *also* legal and
    lands on a different day — "05-04-2023" is 5 April or 4 May, and choosing is
    the same guess about intent ADR-0002 refuses over ``"Appel"``. "22-05-2023"
    stays structural: 22 cannot be a month, so it has one reading. (The first
    version of this function chose day-first silently, which enforced less than
    the ADR claimed — caught by a self-grilling, not by the suite.)
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
    """Ingest ``data/seed.json`` into the configured database.

    Wiring only — every step is covered by its own tests. Safe to re-run: ``persist``
    has replace semantics, so a reseed leaves the database as one seed did.

        python -m scripts.seed
    """
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
    """Record the rentals the seed already describes, above `persist`.

    **This lives here and not in `persist`, deliberately** — the placement is what makes
    ADR-0007 and ADR-0011 simultaneously true. `persist` refuses once rentals exist, and
    `test_reseed_is_idempotent` requires a second `persist` on a fresh database to
    succeed; both hold only if `persist` never writes a rental itself. `app/storage.py`
    also says it makes no decisions, and "an `In Use` row with an assignee is a rental"
    is one.

    Seed id 7 is `In Use` and assigned to an address with no account, so its rental gets
    `account_id = NULL` (ADR-0007). Releasing it instead — which is what Phase 0 did to
    id 2's orphan rental — would destroy the only evidence of who holds the headphones;
    id 2 was released precisely *because* it named nobody.
    """
    from app.rentals import reconcile_held_items

    return reconcile_held_items(session, report.imported)


def seed_if_empty(engine: Engine) -> bool:
    """Seed the database only if it holds no hardware items. Returns whether it did.

    **A deploy shim, not a migration strategy** (see `BACKLOG.md`). The deploy
    target offers no way to run a one-off command against the mounted volume, so
    the only remaining place to seed a fresh instance is startup.

    The emptiness check is what makes that safe rather than merely convenient.
    ``persist`` has replace semantics, so an unguarded boot seed would wipe the
    table on every restart. Once the rental engine exists the table is never empty,
    so this can never reach a database with rentals in it.
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


# Last in the file, deliberately. Running `python -m scripts.seed` executes the module top
# to bottom, so `main()` may only be called once every name it reaches is bound. This block
# used to sit directly under `main`, above `_create_rentals_schema` and `_open_seed_rentals`
# — importing the module bound them and every test passed, while the README's own setup
# step died on a `NameError`. Found by a fresh-clone check, not by the suite.
if __name__ == "__main__":
    main()
