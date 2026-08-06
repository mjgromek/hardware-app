"""Phase 0 — seed ingestion.

Ingestion validates **structure only** (ADR-0002). Every test here asserts on the
``IngestReport`` a caller receives, never on how ``ingest`` arrived at it.

Fixtures are inline and hermetic. The seed's 11 records exist in this repo only as
the defect table in `brainstorm.md` §2, so each test reproduces the one defect it
pins rather than depending on a file that does not exist.

The invariant underneath all of it: **nothing is deleted**. A row that fails
structural validation becomes a quarantine record with a reason; it does not
vanish.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import pytest

from app.domain import HardwareItem, QuarantineRecord, Status
from scripts.seed import ingest, normalise_purchase_date

# Injected rather than read from the clock, so plausibility checks are deterministic.
TODAY = date(2026, 8, 6)


def _record(**overrides: Any) -> dict[str, Any]:
    """A structurally clean seed record, in the seed's own camelCase shape.

    Each test overrides exactly the field carrying the defect it pins, so the
    defect is visible at the call site rather than buried in this helper.
    """
    record: dict[str, Any] = {
        "id": 1,
        "name": "ThinkPad X1 Carbon",
        "brand": "Lenovo",
        "purchaseDate": "2022-03-14",
        "status": "Available",
    }
    record.update(overrides)
    return record


def _imported_by_name(report: Any, name: str) -> HardwareItem:
    matches = [item for item in report.imported if item.name == name]
    assert len(matches) == 1, (
        f"expected exactly one imported hardware item named {name!r}, "
        f"got {[item.name for item in report.imported]}"
    )
    return matches[0]


def _quarantine_for(report: Any, source_id: int) -> QuarantineRecord:
    matches = [rec for rec in report.quarantined if rec.source_id == source_id]
    assert len(matches) == 1, (
        f"expected exactly one quarantine record for source id {source_id}, "
        f"got {[(rec.source_id, rec.reason) for rec in report.quarantined]}"
    )
    return matches[0]


# --------------------------------------------------------------------------
# §2 defect 1 — id `4` appears twice
# --------------------------------------------------------------------------


def test_seed_rekeys_duplicate_id() -> None:
    """A primary-key collision is re-keyed, not dropped and not quarantined.

    §2 handles the duplicate by re-keying the second occurrence to a fresh id and
    preserving the original as ``source_id``. The fixture deliberately contains a
    later record already holding id 12, so a naive "next id is 12" re-key produces
    a second collision.
    """
    records: list[Mapping[str, Any]] = [
        _record(id=4, name="Logitech MX Master 3", brand="Logitech"),
        _record(id=4, name="Samsung Galaxy Tab S8", brand="Samsung"),
        _record(id=12, name="Dell UltraSharp U2723QE", brand="Dell"),
    ]

    report = ingest(records, today=TODAY)

    assert len(report.imported) == 3, (
        "ingestion is loss-free: a duplicate id must re-key, never drop a row"
    )

    ids = [item.id for item in report.imported]
    assert len(set(ids)) == 3, f"imported hardware items must have unique ids, got {ids}"

    first = _imported_by_name(report, "Logitech MX Master 3")
    second = _imported_by_name(report, "Samsung Galaxy Tab S8")
    assert first.id == 4, "the first occurrence keeps the seed id"
    assert second.id != 4, "the second occurrence is re-keyed off the colliding id"
    assert second.source_id == 4, (
        "a re-keyed hardware item preserves its original seed id as source_id"
    )

    assert report.quarantined == (), (
        "a duplicate id is resolved by re-keying, so nothing is quarantined for it; "
        f"got {[(rec.source_id, rec.reason) for rec in report.quarantined]}"
    )


# --------------------------------------------------------------------------
# §2 defect 4 — id `9` carries "22-05-2023" among ISO dates
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2023-05-22", date(2023, 5, 22)),  # already ISO
        ("22-05-2023", date(2023, 5, 22)),  # the seed's stray DD-MM-YYYY
        ("01-02-2020", date(2020, 2, 1)),   # day-first, not month-first
        (None, None),                       # id 10's null date
        ("", None),                         # empty is absent, not invalid
    ],
)
def test_seed_normalises_date_formats(raw: str | None, expected: date | None) -> None:
    """A seed purchase date parses from either format; absence yields None."""
    assert normalise_purchase_date(raw) == expected


def test_seed_imports_non_iso_date_without_quarantining() -> None:
    """A DD-MM-YYYY date is normalised at ingest; the brand typo beside it is not.

    Record 9 carries both defects at once, which is what makes it the test of
    where the boundary sits. Parsing a date field is structural — the field has a
    defined type and two candidate formats. Reading ``"Appel"`` as ``"Apple"`` is a
    guess about intent, correct only because a human recognises the brand, and
    ADR-0002 puts it outside ingestion's remit.
    """
    records = [_record(id=9, name="iPhone 13", brand="Appel", purchaseDate="22-05-2023")]

    report = ingest(records, today=TODAY)

    item = _imported_by_name(report, "iPhone 13")
    assert item.purchase_date == date(2023, 5, 22)
    assert item.brand == "Appel", (
        "ingestion normalises date formats but does not correct spellings "
        f"(ADR-0002) — the typo is the auditor's to surface; got {item.brand!r}"
    )
    assert item.needs_review is False, (
        "a recoverable date format is normalised, so the item is not flagged"
    )
    assert report.quarantined == (), (
        "a normalisable date is not a structural failure; "
        f"got {[(rec.source_id, rec.reason) for rec in report.quarantined]}"
    )


# --------------------------------------------------------------------------
# §2 defect 6 — id `10`: empty brand, null date, off-enum status
# --------------------------------------------------------------------------


def test_seed_quarantines_unknown_status() -> None:
    """An off-enum status is quarantined with a reason, and the item survives flagged.

    ``"Unknown"`` is not a status. The row is not dropped: it becomes a quarantine
    record *and* an imported hardware item carrying ``needs_review``, which blocks
    it from rental (ADR-0003).
    """
    raw = _record(id=10, name="", brand="", purchaseDate=None, status="Unknown")
    records = [raw]

    report = ingest(records, today=TODAY)

    quarantined = _quarantine_for(report, 10)
    assert quarantined.reason.strip(), "a quarantine record must carry a readable reason"
    assert "unknown" in quarantined.reason.lower(), (
        "the reason must name the offending value so an admin can act on it; "
        f"got {quarantined.reason!r}"
    )
    assert dict(quarantined.payload) == raw, (
        "the original row is preserved verbatim — ingestion is loss-free"
    )

    assert len(report.imported) == 1, (
        "the row is still imported; quarantine records the failure, it does not delete"
    )
    item = report.imported[0]
    assert isinstance(item.status, Status), (
        f"the status enum stays closed; got {item.status!r}"
    )
    assert item.status is Status.AVAILABLE, (
        "an off-enum status carries the weakest claim the evidence supports "
        "(ADR-0002): 'Unknown' means unidentifiable, not broken, so it must not "
        f"become Repair; got {item.status!r}"
    )
    assert item.needs_review is True, "an off-enum status maps to needs_review"
    assert item.review_reason, (
        "a flagged item carries the reason it was flagged, or the admin queue is blind"
    )
    assert not item.brand, "an empty brand is nullable, not an ingestion error"
    assert item.purchase_date is None, "a null purchase date is nullable, not an error"


# --------------------------------------------------------------------------
# §2 defect 3 — id `6`: purchaseDate 2027-10-10
# --------------------------------------------------------------------------


def test_seed_flags_future_purchase_date() -> None:
    """A purchase date after today is quarantined and the item is flagged."""
    raw = _record(
        id=6,
        name="Sony WH-1000XM5",
        brand="Sony",
        purchaseDate="2027-10-10",
        status="Available",
    )

    report = ingest([raw], today=TODAY)

    quarantined = _quarantine_for(report, 6)
    assert quarantined.reason.strip(), "a quarantine record must carry a readable reason"
    assert "future" in quarantined.reason.lower(), (
        "the reason must say the purchase date is in the future; "
        f"got {quarantined.reason!r}"
    )
    assert dict(quarantined.payload) == raw, "the original row is preserved verbatim"

    item = _imported_by_name(report, "Sony WH-1000XM5")
    assert item.needs_review is True, (
        "an implausible purchase date flags the item, which blocks rental (ADR-0003)"
    )


def test_seed_accepts_purchase_date_of_today() -> None:
    """Today is not the future — the plausibility check is strictly after ``today``."""
    records = [
        _record(
            id=7,
            name="Anker PowerCore",
            brand="Anker",
            purchaseDate=TODAY.isoformat(),
        )
    ]

    report = ingest(records, today=TODAY)

    item = _imported_by_name(report, "Anker PowerCore")
    assert item.needs_review is False, "an item purchased today is not implausible"
    assert report.quarantined == (), (
        "today's date is valid; "
        f"got {[(rec.source_id, rec.reason) for rec in report.quarantined]}"
    )


# --------------------------------------------------------------------------
# §2 defect 9 — id `2`: In Use with no assignedTo
# --------------------------------------------------------------------------


def test_seed_resolves_orphan_rental() -> None:
    """No imported item is left ``In Use`` with nobody holding it.

    "An item In Use with no renter" is named in CONTEXT.md as an impossible state.
    This asserts the state is unreachable after import without dictating *which*
    resolution ingestion picks.
    """
    records = [
        _record(id=2, name="iPad Air", brand="Apple", status="In Use", assignedTo=None)
    ]

    report = ingest(records, today=TODAY)

    item = _imported_by_name(report, "iPad Air")
    assert not (item.status is Status.IN_USE and not item.assigned_to), (
        "an orphan rental is resolved at import: an item cannot be In Use with no "
        f"renter; got status={item.status!r} assigned_to={item.assigned_to!r}"
    )


# --------------------------------------------------------------------------
# ADR-0002 — the declared boundary of ingestion's remit
# --------------------------------------------------------------------------


def test_seed_ignores_semantic_contradiction_in_notes() -> None:
    """Ingestion does not judge free text.

    The Dell XPS is ``Available`` with notes reading "battery swelling". That
    contradiction is real, and it is the Inventory Auditor's to find (ADR-0002) —
    ADR-0003 keeps it unrentable later. If ingestion ever grows a keyword scan,
    this test is what catches it, and this test is not the one to change.
    """
    records = [
        _record(
            id=5,
            name="Dell XPS 15",
            brand="Dell",
            status="Available",
            notes="Battery swelling, do not issue without service",
        )
    ]

    report = ingest(records, today=TODAY)

    item = _imported_by_name(report, "Dell XPS 15")
    assert item.status is Status.AVAILABLE, (
        "a structurally valid status is imported as-is; semantics are not ingestion's job"
    )
    assert item.needs_review is False, (
        "ingestion flags structural defects only — this record has none"
    )
    assert report.quarantined == (), (
        "a semantic contradiction is not a structural failure; "
        f"got {[(rec.source_id, rec.reason) for rec in report.quarantined]}"
    )
