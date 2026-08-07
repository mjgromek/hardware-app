"""Phase 0 — seed ingestion.

Ingestion validates **structure only** (ADR-0002). Every test here asserts on the
``IngestReport`` a caller receives, never on how ``ingest`` arrived at it.

Fixtures are inline and hermetic: each test reproduces the one defect it pins, so a
red test names a behaviour rather than a row number. The single exception is
``test_importer_reproduces_documented_audit``, which runs the real `data/seed.json`
end to end precisely so that `docs/DATA_AUDIT.md` is falsifiable — if the seed file
or the importer drifts apart from the documented audit, that test goes red.

The invariant underneath all of it: **nothing is deleted**. A row that fails
structural validation becomes a quarantine record with a reason; it does not
vanish.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pytest

from app.domain import HardwareItem, QuarantineRecord, Status
from scripts.seed import AmbiguousDate, ingest, normalise_purchase_date

# Injected rather than read from the clock, so plausibility checks are deterministic.
TODAY = date(2026, 8, 6)

# Resolved from this file, not the CWD, so the suite runs the same from anywhere.
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed.json"


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
        ("22-05-2023", date(2023, 5, 22)),  # the seed's stray DD-MM-YYYY: 22 forces day-first
        ("13-01-2020", date(2020, 1, 13)),  # first field above 12 — one reading
        ("04-04-2023", date(2023, 4, 4)),   # transposition yields the same date — one reading
        (None, None),                       # id 10's null date
        ("", None),                         # empty is absent, not invalid
    ],
)
def test_seed_normalises_date_formats(raw: str | None, expected: date | None) -> None:
    """A purchase date with exactly one legal reading parses; absence yields None."""
    assert normalise_purchase_date(raw) == expected


@pytest.mark.parametrize("raw", ["05-04-2023", "01-02-2020", "12-11-2021"])
def test_ambiguous_date_refuses_to_choose(raw: str) -> None:
    """Both fields could be the month, the readings differ — parsing stops.

    A parse with exactly one legal reading is structural; picking between two is
    the same guess about intent ADR-0002 refuses over ``"Appel"``. The earlier
    version of this suite pinned ``01-02-2020 → 1 February`` as a feature — the
    silent day-first judgment the self-grilling caught.
    """
    with pytest.raises(AmbiguousDate) as excinfo:
        normalise_purchase_date(raw)
    assert len(excinfo.value.readings) == 2, (
        "the refusal names both candidate readings so the quarantine reason can"
    )


def test_seed_quarantines_ambiguous_date() -> None:
    """An ambiguous date quarantines with both readings named, like an off-enum status.

    ``"05-04-2023"`` is 5 April read day-first and 4 May read month-first. The item
    imports with no date — the weakest claim the evidence supports — the original
    value survives verbatim in the quarantine payload, and ``needs_review`` hands
    the ruling to a human (ADR-0003 blocks rental meanwhile).
    """
    records = [_record(id=3, name="Kindle Oasis", purchaseDate="05-04-2023")]

    report = ingest(records, today=TODAY)

    item = _imported_by_name(report, "Kindle Oasis")
    assert item.purchase_date is None, (
        "an ambiguous date must not be stored under either reading; storing one "
        f"is the judgment ADR-0002 forbids — got {item.purchase_date!r}"
    )
    assert item.needs_review is True, (
        "which date is true is an open question only a human can settle"
    )

    record = _quarantine_for(report, 3)
    assert "2023-04-05" in record.reason and "2023-05-04" in record.reason, (
        "the reason must name both readings so the admin ruling on it does not "
        f"have to re-derive the ambiguity; got {record.reason!r}"
    )
    assert record.payload["purchaseDate"] == "05-04-2023", (
        "the original value survives verbatim as evidence"
    )


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


def test_seed_records_orphan_rental_in_quarantine() -> None:
    """Releasing the orphan rental is a divergence from the seed, so it is recorded.

    ``test_seed_resolves_orphan_rental`` pins the repair; this pins the *record* of
    it. Every other divergence between the brief and the database lands in
    ``hardware_quarantine`` with a reason. Without one here, the database silently
    disagrees with the brief about a row it changed, and no admin can find out why.

    The item itself is **not** flagged. It is a usable MacBook; all we lost is the
    name of whoever held it. ``needs_review`` blocks rental (ADR-0003), so flagging
    would punish a perfectly good item for a defect in the paperwork.
    """
    raw = _record(
        id=2,
        name="Apple MacBook Pro 13",
        brand="Apple",
        purchaseDate="2021-12-20",
        status="In Use",
        assignedTo=None,
    )

    report = ingest([raw], today=TODAY)

    quarantined = _quarantine_for(report, 2)
    assert quarantined.reason.strip(), "a quarantine record must carry a readable reason"
    reason = quarantined.reason.lower()
    assert "in use" in reason, (
        "the reason must name the state the seed claimed, or an admin cannot tell "
        f"what was changed; got {quarantined.reason!r}"
    )
    assert any(word in reason for word in ("assign", "renter", "orphan")), (
        "the reason must say that nobody was holding the item — that missing renter "
        f"is the whole defect; got {quarantined.reason!r}"
    )
    assert dict(quarantined.payload) == raw, (
        "the original row is preserved verbatim — ingestion is loss-free"
    )

    assert len(report.imported) == 1, (
        "quarantine records the divergence, it does not withhold the item"
    )
    item = _imported_by_name(report, "Apple MacBook Pro 13")
    assert item.needs_review is False, (
        "an orphan rental is fully repaired by releasing the item, so nothing is "
        "left for a human to decide. needs_review blocks rental (ADR-0003) and this "
        f"item is rentable; got needs_review={item.needs_review!r} "
        f"review_reason={item.review_reason!r}"
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


# --------------------------------------------------------------------------
# §2 as a whole — the documented audit, run against the real seed
# --------------------------------------------------------------------------


def test_importer_reproduces_documented_audit() -> None:
    """`docs/DATA_AUDIT.md` is a claim about `data/seed.json`; this makes it falsifiable.

    The one integration-flavoured test in this file. Every other test builds its own
    row, which keeps failures legible but means none of them would notice if the
    committed seed and the importer drifted apart. This one runs the real file and
    asserts the audit table in `brainstorm.md` §2 line by line.

    ``today`` is injected like everywhere else. Record 6's defect is "purchased in
    the future", which stops being true in October 2027 — a test that quietly
    asserts nothing from then on is worse than no test.
    """
    records = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    assert len(records) == 11, (
        f"the audit is written against the 11 rows committed from the brief; "
        f"{SEED_PATH} now has {len(records)}"
    )

    report = ingest(records, today=TODAY)

    assert len(report.imported) == 11, (
        "nothing is deleted: 11 seed rows in, 11 hardware items out; "
        f"got {len(report.imported)}"
    )

    quarantined_ids = sorted(rec.source_id for rec in report.quarantined)
    assert quarantined_ids == [2, 6, 10], (
        "the audit documents exactly three divergences from the brief — id 2's "
        "orphan rental, id 6's future purchase date, id 10's off-enum status. "
        "Each must leave a quarantine record saying so; "
        f"got {[(rec.source_id, rec.reason) for rec in report.quarantined]}"
    )
    assert "future" in _quarantine_for(report, 6).reason.lower(), (
        "id 6's reason must name the future purchase date; "
        f"got {_quarantine_for(report, 6).reason!r}"
    )
    assert "unknown" in _quarantine_for(report, 10).reason.lower(), (
        "id 10's reason must name the off-enum status; "
        f"got {_quarantine_for(report, 10).reason!r}"
    )
    assert "in use" in _quarantine_for(report, 2).reason.lower(), (
        "id 2's reason must name the orphan rental that was released; "
        f"got {_quarantine_for(report, 2).reason!r}"
    )

    # Defect 1 — id 4 twice. The first keeps the id, the second is re-keyed above
    # every id the seed uses, and carries the original as source_id.
    original = _imported_by_name(report, "SAMSUNG Galaxy S21")
    rekeyed = _imported_by_name(report, "Duplicate ID Test Laptop")
    assert original.id == 4, f"the first occurrence keeps seed id 4; got {original.id}"
    assert rekeyed.id == 12, (
        f"the second occurrence re-keys to 12, above the seed's highest id; "
        f"got {rekeyed.id}"
    )
    assert rekeyed.source_id == 4, (
        f"a re-keyed item preserves its seed id; got {rekeyed.source_id!r}"
    )
    ids = sorted(item.id for item in report.imported)
    assert len(set(ids)) == 11, f"imported ids must be unique; got {ids}"

    # Defect 5 — the brand typo is the auditor's, not ingestion's (ADR-0002).
    ipad = _imported_by_name(report, "iPad Pro 12.9")
    assert ipad.brand == "Appel", (
        f"'Appel' is preserved exactly as the seed wrote it (ADR-0002); "
        f"got {ipad.brand!r}"
    )

    # Defects 7 and 8 — the two semantic contradictions. Structurally spotless, so
    # ingestion imports them untouched; ADR-0003 keeps them unrentable later.
    for name in ("Dell XPS 15 9510", "MacBook Air M2"):
        item = _imported_by_name(report, name)
        assert item.status is Status.AVAILABLE, (
            f"{name} is structurally valid, so its status is imported as-is; "
            f"got {item.status!r}"
        )
        assert item.needs_review is False, (
            f"{name} contradicts itself in free text, which is the auditor's to "
            "catch (ADR-0002). If ingestion ever grows a keyword scan this is what "
            f"catches it; got review_reason={item.review_reason!r}"
        )
