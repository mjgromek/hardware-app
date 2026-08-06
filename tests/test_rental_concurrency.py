"""Phase 2 Slice A — two people reaching for the same laptop at the same moment.

This is the test `app/storage.py`'s docstring, `test_persist_does_not_commit` and
`test_add_hardware_concurrency.py` were all written in service of. Three separate
pieces of Phase 0 and Phase 1 work name it by hand as the reason they are shaped the
way they are; here it finally runs.

**A read-then-write cannot win this.** ADR-0008 is explicit: a guard reads state and
then decides, and both callers pass the same pre-check before either writes. The claim
has to be `UPDATE hardware SET status='In Use' WHERE id=:id AND status='Available'`,
with a rowcount of zero meaning the caller lost. So this test deliberately does not
assert "the guard ran" — it asserts the only thing the guard cannot deliver: that
exactly one of six simultaneous claimants ends up holding the item.

**The loser's reason is `In Use`, not a race.** Also ADR-0008: reasons are one per
cause, never one per timing. By the time the loser is told, "somebody else has it" is
simply the current state, and a client rendering "another user claimed this microsecond
before you" would leak implementation detail as UX.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tests.conftest import rent_path, rental_rows, statuses_by_id

ACCEPTED = (200, 201, 204)

#: Seed id 1: `Available`, unflagged, and nobody's.
CONTESTED_ITEM = 1

CLAIMANTS = 6


def test_concurrent_rent_only_one_succeeds(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """Six simultaneous rents on one item: one winner, five `409`s, one rental row.

    Four assertions, each catching a different way this goes wrong in production.

    *Exactly one success.* Two `201`s mean two people were told the headphones are
    theirs, and only one of them has them.

    *No `500`.* An `IntegrityError` surfacing from the partial unique index is the
    database saving the application, not the application working — and the employee
    who sees "Internal Server Error" has no way to know whether they got the laptop.
    Under SQLite this is also where a `database is locked` would land.

    *One rental row.* The index makes two *active* rentals unreachable, so a broken
    implementation cannot express the failure that way; what it can do is write a
    closed-looking or duplicate row, or write none at all while answering `201`.

    *The loser's reason names `In Use`.* Not "try again", not "conflict" — the same
    reason the sequential `test_cannot_rent_hardware_already_in_use` produces, because
    ADR-0008 refuses to give the race its own vocabulary.

    The requests share one client and therefore one session cookie: the contention is
    over the item, not over who is asking, and six accounts would only add a variable
    that has nothing to do with the lock.
    """
    assert statuses_by_id(admin_client)[CONTESTED_ITEM] == "Available", (
        f"setup: item {CONTESTED_ITEM} must be free before six people reach for it"
    )

    def claim(_: int):
        return user_client.post(rent_path(CONTESTED_ITEM))

    with ThreadPoolExecutor(max_workers=CLAIMANTS) as pool:
        responses = list(pool.map(claim, range(CLAIMANTS)))

    codes = sorted(response.status_code for response in responses)

    crashes = [
        (r.status_code, r.text[:200]) for r in responses if r.status_code >= 500
    ]
    assert not crashes, (
        "no claimant may receive a 5xx. An IntegrityError escaping from the partial "
        "unique index means the race was lost by the application and caught by the "
        "database, and the person who sent it cannot tell whether they got the item. "
        f"Crashes: {crashes}"
    )

    winners = [r for r in responses if r.status_code in ACCEPTED]
    assert len(winners) == 1, (
        f"exactly one of {CLAIMANTS} simultaneous rents may succeed; {len(winners)} "
        f"did. Status codes were {codes}. Two successes means two employees were both "
        "told the item is theirs"
    )

    losers = [r for r in responses if r.status_code not in ACCEPTED]
    assert all(r.status_code == 409 for r in losers), (
        "every claimant who lost must be refused with 409 and not 400, 404 or 500 — "
        "losing a race is a conflict with the item's state, which is what 409 means; "
        f"got {codes}"
    )
    assert all("in use" in r.text.lower() for r in losers), (
        "the losers are told the item is In Use, which by the time they are told is "
        "simply true. ADR-0008 gives one reason per cause and none per timing, so a "
        "distinct 'somebody beat you to it' message here would be implementation "
        f"detail as UX; got {[r.text[:120] for r in losers]}"
    )

    rows = rental_rows(app, CONTESTED_ITEM)
    assert len(rows) == 1, (
        f"one winner leaves one rental row; got {len(rows)}. Fewer means the 2xx was "
        "issued for a claim that was rolled back; more means the log records a rental "
        f"that never happened. Rows: {rows}"
    )
    assert rows[0]["ended_at"] is None, (
        "the surviving rental is the active one; got "
        f"ended_at={rows[0]['ended_at']!r}"
    )
    assert statuses_by_id(admin_client)[CONTESTED_ITEM] == "In Use", (
        "the item ends the race held, not free — a rowcount-0 rollback that undid the "
        "winner as well as the losers would satisfy the counts above and leave the "
        "headphones in nobody's hands"
    )
