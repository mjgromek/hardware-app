"""Phase 0 — persistence, the seam between a pure importer and a database.

``scripts.seed.ingest`` is pure: it returns an ``IngestReport`` and never touches
I/O. ``app.storage`` is the only module that knows a database exists. **That
boundary is what these tests exercise** — a report goes in, hardware items and
quarantine records come back out, and nothing in between may quietly lose a field.

Every assertion here goes through the public surface: ``create_engine_for``,
``create_schema``, ``new_session``, ``persist``, ``load_items``,
``load_quarantine``. None of them opens a connection, reads raw SQL, or inspects
SQLAlchemy metadata — SQLAlchemy is never imported here, not even for a type hint:
``Engine`` and ``Session`` are named through ``app.storage``'s re-exports. Reaching
past the module to verify would test the schema an implementation happens to have
rather than the contract it promises, and would go green on a storage layer that
writes perfect rows nobody can read back.

**The caller owns the transaction, so the tests show the transaction.** ``persist``
does not commit; every test opens its own session, calls ``persist``, and commits in
its own body rather than behind a helper. A reader who wants to know which boundary
a test depends on should be able to see it without leaving the test. That the
boundary is really the caller's — and not one ``persist`` closes behind its own
back — is the single thing ``test_persist_does_not_commit`` exists to pin; every
other test here would pass either way.

**Every read goes through a session other than the one that wrote.** A session that
has just written holds those objects in its identity map, and will hand them back
without asking the database anything — which means a write that never reached SQLite,
or a column that stores ``status`` as a bare string, would still satisfy a same-session
read. Reading through a second session is the assertion that the data is in the
database.

Fixtures are chosen per test, not by habit. Tests that pin *fidelity across a
realistic mix* run the real `data/seed.json` — it is the only fixture that carries a
re-keyed ``source_id``, a normalised DD-MM-YYYY date, a null date, flagged and
unflagged rows, and all three statuses at once, and a hand-rolled imitation of it
would drift. Tests that pin *one field* build a single record inline, so the field
under test is visible at the call site.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

import pytest

from app.domain import HardwareItem, IngestReport, QuarantineRecord, Status
from app.storage import (
    Engine,
    Session,
    create_engine_for,
    create_schema,
    load_items,
    load_quarantine,
    new_session,
    persist,
)
from scripts.seed import ingest

# Injected rather than read from the clock, so the seed's 2027 purchase date stays
# a future date and record 6 keeps the defect these tests rely on.
TODAY = date(2026, 8, 6)

# Resolved from this file, not the CWD, so the suite runs the same from anywhere.
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed.json"


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """A schema-ready engine over a database file this test alone can see.

    ``tmp_path`` is per-test, so no test can observe another's rows and the order
    the suite runs in cannot change a result. Setup — engine, then schema — is
    shared because it is not what any of these tests are about; the transaction
    boundary is, and that stays in the test bodies.

    A file-backed URL, not ``:memory:``, because these tests read through a second
    session and an in-memory SQLite database is per-connection.
    """
    engine = create_engine_for(f"sqlite:///{tmp_path / 'hardware_hub.db'}")
    create_schema(engine)
    return engine


def _seed_report() -> IngestReport:
    """The real seed, ingested. 11 hardware items, 3 quarantine records."""
    records = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return ingest(records, today=TODAY)


def _record(**overrides: Any) -> dict[str, Any]:
    """A structurally clean seed record, in the seed's own camelCase shape."""
    record: dict[str, Any] = {
        "id": 1,
        "name": "ThinkPad X1 Carbon",
        "brand": "Lenovo",
        "purchaseDate": "2022-03-14",
        "status": "Available",
    }
    record.update(overrides)
    return record


def _by_id(items: Iterable[HardwareItem]) -> dict[int, HardwareItem]:
    """Key hardware items by id — nothing here may depend on row order."""
    return {item.id: item for item in items}


def _quarantine_by_source_id(
    records: Iterable[QuarantineRecord],
) -> dict[int | None, QuarantineRecord]:
    return {record.source_id: record for record in records}


def _fingerprint(record: QuarantineRecord) -> tuple[Any, ...]:
    """A comparable, order-independent identity for one quarantine record."""
    return (record.source_id, record.reason, json.dumps(dict(record.payload), sort_keys=True))


def _visible_counts(session: Session) -> tuple[int, int]:
    """What this one session can see: (hardware items, quarantine records).

    Both tables together, because "did the write escape the caller's transaction"
    is a question about the whole write, not about one table.
    """
    return len(load_items(session)), len(load_quarantine(session))


# --------------------------------------------------------------------------
# The report reaches the database at all
# --------------------------------------------------------------------------


def test_report_persists_items_and_quarantine(engine: Engine) -> None:
    """Both halves of a report survive the write, and neither is dropped.

    The real seed, because it is the only fixture where the two tables are
    populated at once and by different code paths — 11 imported items and 3
    quarantine records from the same run. A storage layer that persists hardware
    and forgets quarantine passes any single-table test while deleting exactly the
    rows Phase 0 exists to keep.

    The writing session is committed *and closed* before anything is read, and the
    read runs on a session opened afterwards. That is what makes this a persistence
    test rather than a round trip through an identity map: had ``persist`` merely
    staged objects that the commit never flushed, a same-session read would still
    return all fourteen of them.
    """
    report = _seed_report()

    assert report.imported and report.quarantined, (
        "this test is only meaningful if the seed still produces both halves; got "
        f"{len(report.imported)} imported, {len(report.quarantined)} quarantined"
    )

    writer = new_session(engine)
    persist(report, writer)
    writer.commit()
    writer.close()

    reader = new_session(engine)
    items = load_items(reader)
    quarantined = load_quarantine(reader)
    reader.close()

    assert len(items) == len(report.imported), (
        f"every imported hardware item must be written and readable from a new "
        f"session: the report held {len(report.imported)}, the database returned "
        f"{len(items)}"
    )
    assert len(quarantined) == len(report.quarantined), (
        "nothing from the seed is silently deleted — a quarantine record that does "
        f"not survive persistence is a deletion. The report held "
        f"{len(report.quarantined)}, the database returned {len(quarantined)}"
    )


# --------------------------------------------------------------------------
# The transaction belongs to the caller
# --------------------------------------------------------------------------


def test_persist_does_not_commit(engine: Engine) -> None:
    """``persist`` writes through the caller's session and leaves it uncommitted.

    **Why this is a test and not a style note.** Phase 2's rental engine takes an
    item under an atomic conditional UPDATE — ``UPDATE ... WHERE status =
    'Available'`` — and decides whether the rental happened from the row count,
    inside a transaction it opened and will commit or roll back itself. That is the
    whole mechanism behind ``test_concurrent_rent_only_one_succeeds``: two
    simultaneous requests, exactly one winner. A storage function that commits
    behind the caller's back ends that transaction early, so a second request can
    interleave between the check and the commit, and a later failure in the same
    operation can no longer be undone. The signature ``persist(report, session)``
    exists to make the boundary the caller's; this test is what makes that
    a promise rather than a convention. Phase 2 will be written assuming it, so it
    is pinned here, where the assumption is introduced.

    **It is pinned here because nothing else pins it.** Every other test in this
    file commits the writing session itself, and an implementation that commits
    inside ``persist`` satisfies all of them — the rows are in the database either
    way. That mutation is invisible to the rest of the suite and fatal to Phase 2.

    Two observations, one property, kept apart because they fail differently in
    production. *Isolation*: before the caller commits, no other session may see
    the write — otherwise a concurrent request reads a half-finished operation.
    *Abortability*: after ``rollback``, the write is gone — otherwise an operation
    that fails halfway leaves part of itself behind. The obvious mutation trips
    both, but the message tells you which consequence you lost.

    The third act is a control, and it is not decoration: without it, a ``persist``
    that writes nothing at all would satisfy both assertions above. Asserting that
    the *same* report does land once a caller commits it is what keeps this test
    from being able to pass for the wrong reason.
    """
    report = _seed_report()

    assert report.imported and report.quarantined, (
        "this test is only meaningful if the seed still produces both halves; got "
        f"{len(report.imported)} imported, {len(report.quarantined)} quarantined"
    )

    # Act 1 — written, not committed. The writer is deliberately left open.
    writer = new_session(engine)
    persist(report, writer)

    onlooker = new_session(engine)
    items_before_commit, quarantine_before_commit = _visible_counts(onlooker)
    onlooker.close()

    assert items_before_commit == 0, (
        "persist must not commit: a session other than the writer saw "
        f"{items_before_commit} hardware items while the writer's transaction was "
        "still open. The rental engine's conditional UPDATE is only atomic if the "
        "transaction it opened is still the one holding the row"
    )
    assert quarantine_before_commit == 0, (
        "persist must not commit: a session other than the writer saw "
        f"{quarantine_before_commit} quarantine records before the writer "
        "committed — committing one table behind the caller's back ends the "
        "caller's transaction just as surely as committing both"
    )

    # Act 2 — the caller aborts, and the write goes with it.
    writer.rollback()
    writer.close()

    after_rollback = new_session(engine)
    items_after_rollback, quarantine_after_rollback = _visible_counts(after_rollback)
    after_rollback.close()

    assert items_after_rollback == 0, (
        "rolling back the caller's session must discard everything persist wrote; "
        f"{items_after_rollback} hardware items survived the rollback, which means "
        "persist committed them or wrote them outside the caller's transaction"
    )
    assert quarantine_after_rollback == 0, (
        "rolling back the caller's session must discard the quarantine write too; "
        f"{quarantine_after_rollback} records survived the rollback"
    )

    # Act 3 — control: the same report does land when a caller commits it, so the
    # two assertions above cannot be satisfied by a persist that writes nothing.
    committer = new_session(engine)
    persist(report, committer)
    committer.commit()
    committer.close()

    reader = new_session(engine)
    items_after_commit, quarantine_after_commit = _visible_counts(reader)
    reader.close()

    assert (items_after_commit, quarantine_after_commit) == (
        len(report.imported),
        len(report.quarantined),
    ), (
        "control failed: persist must still write when the caller does commit. "
        f"Expected {len(report.imported)} hardware items and "
        f"{len(report.quarantined)} quarantine records after a committed persist, "
        f"got {items_after_commit} and {quarantine_after_commit} — with nothing "
        "written, the isolation and rollback assertions above prove nothing"
    )


# --------------------------------------------------------------------------
# The fields ingestion worked to establish survive the round trip
# --------------------------------------------------------------------------


def test_persisted_items_round_trip(engine: Engine) -> None:
    """``status``, ``needs_review``, ``source_id`` and ``purchase_date`` come back intact.

    These four are the entire output of Phase 0's ingestion work: the closed enum,
    the rentability guard (ADR-0003), the preserved seed id of a re-keyed row, and
    the normalised date. A lossy round trip discards all of it while still
    reporting the right row count.

    Types matter as much as values. A ``status`` that returns as ``"Available"``
    compares equal to ``Status.AVAILABLE`` — ``Status`` subclasses ``str`` — so a
    value assertion alone would go green on a storage layer that hands the guard
    layer raw strings. The same for a ``purchase_date`` returned as text, which
    sorts and compares wrongly the moment the dashboard orders by it.

    The type checks in particular are only worth anything across a session
    boundary: the objects the writer put in are already correctly typed in memory,
    so reading them back from the writing session would assert on Python, not on
    what SQLite actually stores.
    """
    report = _seed_report()

    writer = new_session(engine)
    persist(report, writer)
    writer.commit()
    writer.close()

    reader = new_session(engine)
    loaded = _by_id(load_items(reader))
    reader.close()

    assert sorted(loaded) == sorted(item.id for item in report.imported), (
        "hardware items must round-trip under their own ids; got "
        f"{sorted(loaded)} back from {sorted(item.id for item in report.imported)}"
    )

    for expected in report.imported:
        actual = loaded[expected.id]
        for field in ("status", "needs_review", "source_id", "purchase_date"):
            assert getattr(actual, field) == getattr(expected, field), (
                f"hardware item {expected.id} ({expected.name!r}) lost {field} in "
                f"storage: ingestion established {getattr(expected, field)!r}, the "
                f"database returned {getattr(actual, field)!r}"
            )

    # The re-keyed row: the seed's second `id: 4`, which is the only reason
    # `source_id` exists. It is also the row a naive round trip is likeliest to
    # flatten, since every other item has `source_id` None.
    rekeyed = next(item for item in report.imported if item.source_id is not None)
    assert loaded[rekeyed.id].source_id == rekeyed.source_id, (
        f"the re-keyed hardware item must keep its original seed id: expected "
        f"source_id {rekeyed.source_id!r}, got {loaded[rekeyed.id].source_id!r}"
    )

    for item in loaded.values():
        assert isinstance(item.status, Status), (
            f"status must come back as a Status member, not a raw value — the enum "
            f"stays closed on the way out of the database as well as into it; "
            f"hardware item {item.id} returned {item.status!r} "
            f"({type(item.status).__name__})"
        )
        assert item.purchase_date is None or isinstance(item.purchase_date, date), (
            f"a normalised purchase date must come back as a date, not the string "
            f"it was parsed from — otherwise ingestion's normalisation is undone at "
            f"the database boundary; hardware item {item.id} returned "
            f"{item.purchase_date!r} ({type(item.purchase_date).__name__})"
        )


# --------------------------------------------------------------------------
# Reseeding a deployed instance
# --------------------------------------------------------------------------


def test_reseed_is_idempotent(engine: Engine) -> None:
    """Seeding twice leaves the database as seeding once did.

    ``persist`` specifies replace semantics: a reseed replaces the quarantine trail
    rather than accumulating onto it. A documented reseed is an operation on a live
    instance, so the second run has to be safe. Two failure modes are pinned
    separately because they read differently: duplicated hardware would give a
    dashboard two of every item, and quarantine records that duplicate — or are
    wiped and only partly rewritten — break the audit trail that makes ingestion
    loss-free.

    Each reseed is its own committed transaction, as it would be on a deployment,
    and each observation is its own session. A session held open across the second
    persist could serve the first run's objects out of its identity map and report
    a clean replace that never happened.
    """
    report = _seed_report()

    first = new_session(engine)
    persist(report, first)
    first.commit()
    first.close()

    after_first = new_session(engine)
    items_after_first = load_items(after_first)
    quarantine_after_first = load_quarantine(after_first)
    after_first.close()

    second = new_session(engine)
    persist(report, second)
    second.commit()
    second.close()

    after_second = new_session(engine)
    items_after_second = load_items(after_second)
    quarantine_after_second = load_quarantine(after_second)
    after_second.close()

    assert len(items_after_second) == len(items_after_first), (
        f"a reseed must not duplicate hardware items: {len(items_after_first)} "
        f"after one persist, {len(items_after_second)} after two"
    )
    assert sorted(item.id for item in items_after_second) == sorted(
        item.id for item in items_after_first
    ), (
        "a reseed leaves the same hardware items under the same ids; got "
        f"{sorted(item.id for item in items_after_second)} where "
        f"{sorted(item.id for item in items_after_first)} was expected"
    )

    assert Counter(map(_fingerprint, quarantine_after_second)) == Counter(
        map(_fingerprint, quarantine_after_first)
    ), (
        "a reseed neither duplicates nor drops quarantine records — replace "
        "semantics mean a second run that doubles the audit trail is as wrong as "
        "one that clears it; got "
        f"{[(rec.source_id, rec.reason) for rec in quarantine_after_second]} where "
        f"{[(rec.source_id, rec.reason) for rec in quarantine_after_first]} was expected"
    )


# --------------------------------------------------------------------------
# A quarantine record without its reason is an unexplained deletion
# --------------------------------------------------------------------------


def test_quarantine_reason_is_retrievable(engine: Engine) -> None:
    """The reason a row was quarantined survives to the reader.

    Inline, not the seed: this pins one field on one record, and the record that
    produces it — the off-enum ``"Unknown"`` status — should be readable at the
    call site rather than looked up by row number.

    The reason is the entire justification for the table. A quarantine row that
    comes back without one tells an admin that something was rejected and nothing
    about what or why, which is a silent deletion wearing a record's clothes.
    """
    raw = _record(id=10, name="Unknown Device", brand="", purchaseDate=None, status="Unknown")
    report = ingest([raw], today=TODAY)

    expected = report.quarantined[0]
    assert expected.reason.strip(), (
        "this test is only meaningful if ingestion produced a reason to persist"
    )

    writer = new_session(engine)
    persist(report, writer)
    writer.commit()
    writer.close()

    reader = new_session(engine)
    loaded = _quarantine_by_source_id(load_quarantine(reader))
    reader.close()

    assert 10 in loaded, (
        "the quarantine record must be readable under the seed id it came from, or "
        f"an admin cannot trace it back to a row in the brief; got {sorted(loaded)}"
    )
    record = loaded[10]
    assert record.reason == expected.reason, (
        "the reason must round-trip verbatim: ingestion wrote "
        f"{expected.reason!r}, the database returned {record.reason!r}"
    )
    assert "unknown" in record.reason.lower(), (
        "the persisted reason still names the offending value — truncating or "
        f"rewriting it on the way in defeats the point; got {record.reason!r}"
    )


def test_quarantine_payload_round_trips_as_the_original_row(engine: Engine) -> None:
    """The rejected row itself is kept, verbatim, alongside its reason.

    ``load_quarantine`` promises the payload comes back as the original seed row.
    The reason explains the rejection; the payload is the evidence for it, and
    without it a quarantine record cannot be re-examined or re-imported by hand.

    The fixture carries a null and an empty string on purpose — those are the
    values a serialisation round trip is likeliest to turn into ``"None"``,
    ``"null"``, or nothing at all.
    """
    raw = _record(id=10, name="Unknown Device", brand="", purchaseDate=None, status="Unknown")
    report = ingest([raw], today=TODAY)

    writer = new_session(engine)
    persist(report, writer)
    writer.commit()
    writer.close()

    reader = new_session(engine)
    loaded = _quarantine_by_source_id(load_quarantine(reader))
    reader.close()

    assert 10 in loaded, (
        "there is no payload to check if the quarantine record did not survive "
        f"persistence at all; got {sorted(loaded)}"
    )

    payload: Mapping[str, Any] = loaded[10].payload
    assert dict(payload) == raw, (
        "the quarantined row is preserved exactly as the seed wrote it — ingestion "
        f"is loss-free and so is storage; expected {raw!r}, got {dict(payload)!r}"
    )
