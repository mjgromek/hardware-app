"""Phase 2 Slice A — renting, returning, and every way both are refused.

Nine of these thirteen tests are refusals, which is the right ratio for a phase whose
premise is that guards make impossible states unreachable (CONTEXT.md). "A user can
rent a laptop" is a feature; "two users cannot rent the same laptop, an admin cannot
end somebody's rental without saying why, and a flagged machine goes to nobody" is the
product.

**Every refusal test carries a control.** A route that answers `409` to everybody
satisfies every refusal assertion ever written while shipping an inventory nobody can
borrow from — and that failure mode is invisible in a UI where the button is greyed
out anyway. The control is the identical request in the circumstance that should
succeed, in the same test, because a control in another file is a control nobody
notices has gone.

**Refusals are also asserted by consequence.** The status code is half the claim; the
other half is that the database did not move. A handler that inserts the rental and
*then* decides to answer `409` passes a status-code-only test having already done the
damage, and it is the same shape of bug `test_non_admin_cannot_create_user` was written
to catch in Phase 1.

`409` and not `403`: an employee is permitted to rent hardware, and a laptop in
`Repair` is not a permissions problem. `403` here would tell the Vue client to render
"you may not do this" for a rule that will stop applying the moment somebody returns
the item (ADR-0005 draws the same line for the last admin).

**On `test_cannot_rent_flagged_hardware` and the Dell XPS.** ADR-0003 says that test
asserts "the Dell XPS specifically remains unrentable". It cannot, and the ADR is
wrong about its own example: ingestion is structural only (ADR-0002), so the Dell XPS's
"battery swelling" note is left for the Phase 3 auditor and the item imports
**unflagged**. The two items ingestion actually flags are seed id 6 (2027 purchase
date) and seed id 10 (off-enum status). This test therefore derives the flagged set
from the inventory rather than naming a row, which is both honest about what the seed
produces and correct if Phase 3's auditor starts setting the flag itself. See
`BACKLOG.md`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    ADMIN_EMAIL,
    ANONYMOUS_REFUSAL,
    HARDWARE_PATH,
    force_return_path,
    items_by_id,
    missing_columns,
    rent_path,
    rental_rows,
    return_path,
    statuses_by_id,
    USER_EMAIL,
)

#: Statuses a completed transition may be reported with. Which of the three a rent
#: answers with carries no product meaning; see `tests/conftest.py`.
ACCEPTED = (200, 201, 204)

#: Seed id 1, the iPhone: `Available` and unflagged, so a refusal against it is never
#: the status guard or the review guard firing by accident.
RENTABLE_ITEM = 1

#: Seed id 4, the Galaxy S21 — a second `Available` unflagged row, for the tests that
#: need two items in flight at once.
SECOND_RENTABLE_ITEM = 4

#: Seed id 3, the Razer mouse: the only `Repair` row that is not the re-keyed duplicate.
REPAIR_ITEM = 3

#: Seed id 7, the Sony headphones: `In Use` at import, assigned to an address with no
#: account behind it. The rental ADR-0007 imports with `account_id = NULL`.
HELD_ITEM = 7
SEED_RENTER_EMAIL = "j.doe@booksy.com"

#: An id the seed cannot have produced — 11 rows, one re-keyed to 12.
NO_SUCH_ITEM = 9999

#: The columns `docs/specs/phase-2.md` fixes for one rental row.
RENTAL_COLUMNS = (
    "id",
    "item_id",
    "account_id",
    "renter_email",
    "started_at",
    "ended_at",
    "closed_by_account_id",
    "closed_by_email",
    "close_kind",
)


def _active(rows: list[dict]) -> list[dict]:
    """The rentals with no end yet. `NULL` means active (ADR-0007)."""
    return [row for row in rows if row.get("ended_at") is None]


# --------------------------------------------------------------------------
# Renting is refused, one reason per cause (ADR-0008)
# --------------------------------------------------------------------------


def test_cannot_rent_hardware_in_repair(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """An item in `Repair` goes to nobody, and the refusal says so.

    The reason has to name the cause and not just the outcome. ADR-0008 fixes one
    reason per cause rather than one per timing, so "this item is in Repair" and "this
    item is already in use" must be distinguishable by the person reading the toast —
    a single "unavailable" for both is the vocabulary that ADR rules out.

    The last act is the control. Without it, `return 409` from an unimplemented route
    satisfies everything above.
    """
    before = statuses_by_id(admin_client)
    assert before.get(REPAIR_ITEM) == "Repair", (
        f"setup: seed item {REPAIR_ITEM} must import as Repair for this guard to have "
        f"anything to refuse; got {before.get(REPAIR_ITEM)!r}"
    )

    response = user_client.post(rent_path(REPAIR_ITEM))

    assert response.status_code == 409, (
        f"renting an item in Repair must be refused with 409 — the request is "
        f"well-formed and the employee is permitted to rent hardware, the item is "
        f"not available to rent. POST {rent_path(REPAIR_ITEM)} returned "
        f"{response.status_code}: {response.text}"
    )
    assert "repair" in response.text.lower(), (
        "the 409 carries a readable reason naming the cause (CONTEXT.md, ADR-0008), "
        "or the dashboard toast tells the employee nothing they can act on; got "
        f"{response.text!r}"
    )
    assert statuses_by_id(admin_client)[REPAIR_ITEM] == "Repair", (
        "the refused rent must leave the status alone; the item is no longer in "
        "Repair, which means the UPDATE ran before the guard did"
    )
    assert not rental_rows(app, REPAIR_ITEM), (
        "the refused rent must not have written a rental row — a handler that "
        "inserts and then answers 409 has already recorded that somebody took a "
        f"broken mouse home; got {rental_rows(app, REPAIR_ITEM)}"
    )

    allowed = user_client.post(rent_path(RENTABLE_ITEM))
    assert allowed.status_code in ACCEPTED, (
        "control failed: an Available unflagged item must be rentable. Got "
        f"{allowed.status_code}: {allowed.text}. If renting is refused for every "
        "item, the refusal above proves nothing"
    )


def test_cannot_rent_flagged_hardware(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """`needs_review` blocks rental, for every flagged item and not just the first.

    ADR-0003 exists because the flag was decoration: it appeared in an admin queue and
    changed nothing about what the system would allow. This is the test that makes it
    load-bearing.

    Both flagged rows are checked, derived from the inventory rather than hardcoded —
    see the module docstring on why the ADR's own example (the Dell XPS) is not one of
    them. Each is asserted to be `Available` first, which is what makes the refusal
    attributable to the flag: a flagged item that also happened to be in `Repair`
    would be refused by the wrong guard and this test would never know.
    """
    inventory = items_by_id(admin_client)
    flagged = sorted(
        item_id for item_id, item in inventory.items() if item["needs_review"]
    )
    assert flagged, (
        "setup: ingestion must flag at least one seed row, or this test passes "
        "vacuously; no item came back with needs_review set"
    )

    for item_id in flagged:
        assert inventory[item_id]["status"] == "Available", (
            f"setup: flagged item {item_id} must be Available, or a refusal cannot be "
            f"attributed to the flag rather than to the status guard; it is "
            f"{inventory[item_id]['status']!r}"
        )

        response = user_client.post(rent_path(item_id))

        assert response.status_code == 409, (
            f"a flagged item cannot be rented (ADR-0003) — item {item_id} is "
            f"Available and was flagged at import, and renting it returned "
            f"{response.status_code}: {response.text}"
        )
        assert "review" in response.text.lower(), (
            "the reason must name the flag as the cause, so the employee learns why "
            "an item that reads Available will not come to them (ADR-0008: one "
            f"reason per cause); got {response.text!r}"
        )
        assert not rental_rows(app, item_id), (
            f"the refused rent must not have written a rental row for item {item_id}"
        )
        assert statuses_by_id(admin_client)[item_id] == "Available", (
            f"the refused rent must not have moved item {item_id} to In Use"
        )

    allowed = user_client.post(rent_path(RENTABLE_ITEM))
    assert allowed.status_code in ACCEPTED, (
        "control failed: an unflagged Available item must still be rentable. Got "
        f"{allowed.status_code}: {allowed.text}"
    )


def test_cannot_rent_hardware_already_in_use(
    app, user_client: TestClient, other_user_client: TestClient
) -> None:
    """One item, one holder — whether the rental began in this request or in the seed.

    Two sources of "already held", because they reach the guard through different
    state. The seed's item 7 arrives `In Use` from import with no account behind it;
    `RENTABLE_ITEM` becomes `In Use` because somebody just rented it a millisecond ago.
    An implementation that only consults `hardware.status` passes both; one that only
    consults `rentals` fails the seed case unless ADR-0007's import row was really
    written, which is the join this test happens to also cover.

    The row count is the discriminating assertion. "The second request got a 409" is
    also true of a handler that inserted a second rental and then noticed — and the
    partial unique index (`ON rentals(item_id) WHERE ended_at IS NULL`) exists
    precisely so that two active rentals on one item are unreachable rather than
    merely unlikely.

    The seed's item is attempted first deliberately: it is held from import and needs
    no arranging, so this test's own claim is the first thing that can fail here
    rather than a rent that was only scaffolding for it.
    """
    seed_held = other_user_client.post(rent_path(HELD_ITEM))
    assert seed_held.status_code == 409, (
        f"seed item {HELD_ITEM} arrives In Use and held by {SEED_RENTER_EMAIL}, so it "
        f"is not available to anybody; got {seed_held.status_code}: {seed_held.text}"
    )
    assert len(_active(rental_rows(app, HELD_ITEM))) == 1, (
        f"the refused rent must not have opened a second rental on item {HELD_ITEM}; "
        f"got {_active(rental_rows(app, HELD_ITEM))}"
    )

    first = user_client.post(rent_path(RENTABLE_ITEM))
    second = other_user_client.post(rent_path(RENTABLE_ITEM))

    assert second.status_code == 409, (
        "a second employee must be refused an item somebody is already holding — the "
        f"first employee's rent answered {first.status_code} and this one answered "
        f"{second.status_code}: {second.text}"
    )
    assert len(_active(rental_rows(app, RENTABLE_ITEM))) == 1, (
        "exactly one active rental may exist for an item — two is the impossible "
        "state CONTEXT.md names and the partial unique index forbids; got "
        f"{_active(rental_rows(app, RENTABLE_ITEM))}"
    )

    allowed = other_user_client.post(rent_path(SECOND_RENTABLE_ITEM))
    assert allowed.status_code in ACCEPTED, (
        "control failed: the second employee must be able to rent a *different* "
        f"Available item. Got {allowed.status_code}: {allowed.text}. Otherwise the "
        "refusals above are consistent with 'this account may not rent anything'"
    )


def test_cannot_rent_an_item_that_does_not_exist(
    app, user_client: TestClient
) -> None:
    """An unknown id is `404`, not `409` and not a rental against nothing.

    The unknown-item case is in `app/guards.py`'s remit per the spec, and it is the
    one guard whose answer is *not* `409`: nothing conflicts, the thing is simply not
    there. Getting this wrong in the other direction is worse than cosmetic — a rent
    that inserts a row for an id no hardware table has is exactly the orphan
    `PRAGMA foreign_keys=ON` is the belt behind (ADR-0011).
    """
    response = user_client.post(rent_path(NO_SUCH_ITEM))

    assert response.status_code == 404, (
        f"renting an id that is not in the inventory must be 404; got "
        f"{response.status_code}: {response.text}"
    )
    assert not rental_rows(app, NO_SUCH_ITEM), (
        "no rental row may be written against an item that does not exist; got "
        f"{rental_rows(app, NO_SUCH_ITEM)}"
    )


# --------------------------------------------------------------------------
# Returning
# --------------------------------------------------------------------------


def test_cannot_return_hardware_not_rented(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """Returning an item nobody has taken is refused, and changes nothing.

    Left unguarded this is not a harmless no-op: the obvious implementation closes
    "the active rental" for the item, finds none, and still writes
    `status = 'Available'` — so a `Repair` item quietly becomes rentable through the
    return route, without an admin and without an audit trail. That is why the
    `Repair` item is checked here too, and why the assertion is on the status
    afterwards rather than only on the code.
    """
    before = statuses_by_id(admin_client)
    assert before.get(RENTABLE_ITEM) == "Available", (
        f"setup: item {RENTABLE_ITEM} must start Available and unrented; got "
        f"{before.get(RENTABLE_ITEM)!r}"
    )

    response = user_client.post(return_path(RENTABLE_ITEM))

    assert response.status_code == 409, (
        f"returning an item that is not rented must be refused with 409; got "
        f"{response.status_code}: {response.text}"
    )
    assert not rental_rows(app, RENTABLE_ITEM), (
        "a refused return must not invent a rental row to close; got "
        f"{rental_rows(app, RENTABLE_ITEM)}"
    )

    repaired = user_client.post(return_path(REPAIR_ITEM))
    assert repaired.status_code == 409, (
        f"returning an item in Repair must be refused too; got "
        f"{repaired.status_code}: {repaired.text}"
    )
    assert statuses_by_id(admin_client) == before, (
        "neither refused return may have changed a status — a return route that "
        "writes Available regardless of whether it closed anything is a way to "
        f"release a Repair item without an admin. Got {statuses_by_id(admin_client)}"
    )

    rented = user_client.post(rent_path(RENTABLE_ITEM))
    assert rented.status_code in ACCEPTED, (
        f"control setup: renting must work; got {rented.status_code}: {rented.text}"
    )
    allowed = user_client.post(return_path(RENTABLE_ITEM))
    assert allowed.status_code in ACCEPTED, (
        "control failed: the renter must be able to return an item they hold. Got "
        f"{allowed.status_code}: {allowed.text}. If return refuses everything, the "
        "refusals above prove nothing"
    )


def test_cannot_return_someone_elses_rental(
    app,
    user_client: TestClient,
    other_user_client: TestClient,
    admin_client: TestClient,
) -> None:
    """The wrong-renter guard on `return` is absolute — including for an admin.

    Including the admin is the point of the test, not a bonus case. ADR-0009 keeps
    `return` and `force_return` as two verbs so that this test's name stays true:
    fold admins into the ordinary verb and the name means "a *user* cannot return
    someone else's rental", which is half of what a reviewer reads it as. The admin's
    route to the same outcome is `force-return`, it requires a reason, and it leaves
    an audit event — none of which is true of what is attempted here.

    Refusing the admin here is also what makes `test_force_return_writes_an_audit_event`
    meaningful: if `return` worked for an admin, every admin would use it and the audit
    table would be empty in exactly the cases it exists for.

    The seed's rental is attempted first because *everybody* is the wrong renter for
    it — nobody can authenticate as `j.doe@booksy.com` — so the guard can be exercised
    before any rental has to be arranged.
    """
    seed_held = user_client.post(return_path(HELD_ITEM))
    assert seed_held.status_code == 409, (
        f"nobody can be the renter of seed item {HELD_ITEM}: it is held by "
        f"{SEED_RENTER_EMAIL}, an address with no account, so every ordinary return "
        f"against it is a wrong-renter return; got {seed_held.status_code}: "
        f"{seed_held.text}"
    )
    assert len(_active(rental_rows(app, HELD_ITEM))) == 1, (
        f"the refused return must leave seed item {HELD_ITEM}'s rental open; got "
        f"{rental_rows(app, HELD_ITEM)}"
    )

    rented = user_client.post(rent_path(RENTABLE_ITEM))
    intruder = other_user_client.post(return_path(RENTABLE_ITEM))

    assert intruder.status_code == 409, (
        "an employee must not be able to close a rental they do not hold — the "
        f"renter's own rent answered {rented.status_code} and the colleague's return "
        f"answered {intruder.status_code}: {intruder.text}"
    )
    assert len(_active(rental_rows(app, RENTABLE_ITEM))) == 1, (
        "the refused return must leave the rental open — a handler that closes the "
        "row and then answers 409 has already lost the record of who holds the "
        f"laptop; got {rental_rows(app, RENTABLE_ITEM)}"
    )

    by_admin = admin_client.post(return_path(RENTABLE_ITEM))
    assert by_admin.status_code == 409, (
        "an admin gets the same refusal from the ordinary return verb: ADR-0009 gives "
        "them `force-return`, which takes a reason and writes an audit event. Got "
        f"{by_admin.status_code}: {by_admin.text}"
    )
    assert len(_active(rental_rows(app, RENTABLE_ITEM))) == 1, (
        "the admin's refused return must leave the rental open too"
    )
    assert statuses_by_id(admin_client)[RENTABLE_ITEM] == "In Use", (
        "the item is still held after two refused returns, or the status and the "
        "rental log have drifted apart (ADR-0007's accepted trade-off is that they "
        "must not)"
    )

    allowed = user_client.post(return_path(RENTABLE_ITEM))
    assert allowed.status_code in ACCEPTED, (
        "control failed: the actual renter must be able to return their own item. "
        f"Got {allowed.status_code}: {allowed.text}"
    )


def test_rent_then_return_restores_available(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """A full cycle puts the item back into circulation, in both tables.

    ADR-0007 accepts one trade-off explicitly: `hardware.status` and `rentals` can
    disagree if a write path forgets one of them, and this is the test named as what
    notices. So both are asserted at both ends — status *and* whether an active rental
    row exists.

    The last act is what makes "back to Available" mean something. A label that reads
    `Available` over a rental row still marked active is an item the next employee
    cannot actually take, and re-renting it is the only way to tell the difference.
    """
    assert statuses_by_id(admin_client)[RENTABLE_ITEM] == "Available", (
        f"setup: item {RENTABLE_ITEM} must start Available"
    )

    rented = user_client.post(rent_path(RENTABLE_ITEM))
    assert rented.status_code in ACCEPTED, (
        f"renting an Available unflagged item must succeed; got {rented.status_code}: "
        f"{rented.text}"
    )
    assert statuses_by_id(admin_client)[RENTABLE_ITEM] == "In Use", (
        "a rented item must read In Use to everybody else, or the dashboard offers it "
        "to the next employee who looks"
    )
    assert len(_active(rental_rows(app, RENTABLE_ITEM))) == 1, (
        "renting writes exactly one active rental row; got "
        f"{rental_rows(app, RENTABLE_ITEM)}"
    )

    returned = user_client.post(return_path(RENTABLE_ITEM))
    assert returned.status_code in ACCEPTED, (
        f"the renter must be able to return it; got {returned.status_code}: "
        f"{returned.text}"
    )
    assert statuses_by_id(admin_client)[RENTABLE_ITEM] == "Available", (
        "a returned item goes back to Available; got "
        f"{statuses_by_id(admin_client)[RENTABLE_ITEM]!r}"
    )
    assert not _active(rental_rows(app, RENTABLE_ITEM)), (
        "the rental must be closed as well as the status reset — an active row under "
        "an Available label is the drift ADR-0007 accepts the risk of and this test "
        f"exists to catch; got {rental_rows(app, RENTABLE_ITEM)}"
    )

    again = user_client.post(rent_path(RENTABLE_ITEM))
    assert again.status_code in ACCEPTED, (
        "a returned item must be rentable again — 'restores Available' is a claim "
        f"about circulation, not about a string. Got {again.status_code}: {again.text}"
    )


def test_rental_history_records_both_ends(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """One row per cycle, carrying who took it, who brought it back, and when.

    Settled in `docs/specs/phase-2.md`: after a rent→return cycle the row has a
    non-null `started_at` *and* `ended_at`, the renter fields match who rented, the
    `closed_by` fields match who returned, and `close_kind` is `return`. **One row,
    not two** — the log is the rental, not an event stream.

    The discriminating half is the second cycle. An implementation that `UPDATE`s a
    single row per item in place satisfies every assertion about the first cycle and
    silently loses it on the second, so the history an incident asks about goes back
    exactly one rental. Two cycles, two rows, both closed.

    Read through raw SQL rather than an endpoint because Slice A ships no read surface
    for `rentals`; see `tests/conftest.py`. The columns come from the spec's schema
    table and are checked as a set first, so a missing column says so instead of
    raising inside an assertion about something else.
    """
    cycles = [
        (
            user_client.post(rent_path(RENTABLE_ITEM)).status_code,
            user_client.post(return_path(RENTABLE_ITEM)).status_code,
        )
        for _ in range(2)
    ]

    rows = rental_rows(app, RENTABLE_ITEM)
    assert len(rows) == 2, (
        "two rent→return cycles leave two rental rows: the log is append-only, so an "
        "implementation that updates one row per item in place reports one cycle of "
        f"history however many happened. Got {len(rows)} row(s): {rows}. The two "
        f"cycles answered (rent, return) = {cycles}"
    )

    for row in rows:
        absent = missing_columns(row, *RENTAL_COLUMNS)
        assert not absent, (
            f"the rentals row is missing {absent} — `docs/specs/phase-2.md` fixes the "
            f"schema as {list(RENTAL_COLUMNS)}; got {sorted(row)}"
        )

        assert row["started_at"], (
            f"every rental records when it began; got {row['started_at']!r}"
        )
        assert row["ended_at"], (
            "a returned rental records when it ended — a NULL `ended_at` is what "
            "'active' means (ADR-0007), so a closed rental left NULL keeps the item "
            f"unrentable forever; got {row['ended_at']!r}"
        )
        assert str(row["ended_at"]) >= str(row["started_at"]), (
            "a rental cannot end before it began; got started_at="
            f"{row['started_at']!r}, ended_at={row['ended_at']!r}"
        )

        assert row["renter_email"] == USER_EMAIL, (
            "the renter is snapshotted on the row so that deleting the employee "
            f"cannot erase who held the laptop (ADR-0007); got "
            f"{row['renter_email']!r}, expected {USER_EMAIL!r}"
        )
        assert row["account_id"] is not None, (
            "a rental taken by a signed-in account records that account's id as well "
            "as the email snapshot; NULL is reserved for the seed's accountless "
            "rental (ADR-0007)"
        )
        assert row["closed_by_email"] == USER_EMAIL, (
            "the closer is recorded separately from the renter, because ADR-0009 lets "
            "them be different people; here they are the same person and the field "
            f"must still be filled in. Got {row['closed_by_email']!r}"
        )
        assert row["closed_by_account_id"] == row["account_id"], (
            "the renter closed their own rental, so the two account ids match; got "
            f"closed_by_account_id={row['closed_by_account_id']!r} against "
            f"account_id={row['account_id']!r}"
        )
        assert row["close_kind"] == "return", (
            "an ordinary return is recorded as `return`, not `force_return` — the "
            "distinction is the whole reason the column exists (ADR-0009); got "
            f"{row['close_kind']!r}"
        )

    assert len({row["id"] for row in rows}) == 2, (
        f"the two cycles must be two distinct rows; got ids {[r['id'] for r in rows]}"
    )


# --------------------------------------------------------------------------
# Force-return — the admin's verb (ADR-0009)
# --------------------------------------------------------------------------


def test_admin_force_return_ends_someone_elses_rental(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """An admin can recall a laptop, and the record says it was them who did it.

    Its own test rather than a case inside `test_cannot_return_someone_elses_rental`
    (settled in `docs/specs/phase-2.md`): the two assert opposite outcomes for the
    same request shape, and merging them would make the wrong-renter test's name a lie
    for half its body.

    `close_kind` is the assertion with teeth. An implementation that force-returns by
    calling the ordinary return path with the guard skipped produces a closed rental
    that is indistinguishable from one the employee handed back, and the incident
    review that asks "did she return it or did we take it off her?" gets the wrong
    answer from a table that looks complete.
    """
    rented = user_client.post(rent_path(RENTABLE_ITEM))
    response = admin_client.post(
        force_return_path(RENTABLE_ITEM), json={"reason": "Recalled for battery service"}
    )

    assert response.status_code in ACCEPTED, (
        f"an admin with a reason must be able to end another employee's rental; POST "
        f"{force_return_path(RENTABLE_ITEM)} returned {response.status_code}: "
        f"{response.text} (the employee's rent answered {rented.status_code})"
    )
    assert statuses_by_id(admin_client)[RENTABLE_ITEM] == "Available", (
        "a force-returned item is back in circulation; got "
        f"{statuses_by_id(admin_client)[RENTABLE_ITEM]!r}"
    )

    rows = rental_rows(app, RENTABLE_ITEM)
    assert len(rows) == 1, f"one rental, one row; got {rows}"
    row = rows[0]
    absent = missing_columns(row, *RENTAL_COLUMNS)
    assert not absent, f"the rentals row is missing {absent}; got {sorted(row)}"

    assert row["ended_at"], "the force-returned rental must be closed"
    assert row["renter_email"] == USER_EMAIL, (
        f"the renter stays who it was; got {row['renter_email']!r}"
    )
    assert row["closed_by_email"] == ADMIN_EMAIL, (
        "the closer is the admin who recalled it, not the employee who had it — this "
        "is the field that distinguishes a recall from a hand-back; got "
        f"{row['closed_by_email']!r}"
    )
    assert row["close_kind"] == "force_return", (
        f"a recall is recorded as `force_return`; got {row['close_kind']!r}"
    )

    reclaimed = user_client.post(rent_path(RENTABLE_ITEM))
    assert reclaimed.status_code in ACCEPTED, (
        "control failed: a force-returned item must be genuinely rentable again, not "
        f"left in a state only an admin can clear. Got {reclaimed.status_code}: "
        f"{reclaimed.text}"
    )


def test_force_return_requires_a_reason(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """No reason, no recall — and a reason of spaces is not a reason.

    ADR-0010 accepts that a mandatory reason can be typed as "ok"; the field cannot
    force thought, only a record that somebody was asked. What it must not accept is
    the empty string, because that is the value a UI sends when nobody was asked at
    all, and it produces an audit row that says an admin took a laptop off an employee
    for no stated cause.

    Whitespace specifically, because `min_length=1` is satisfied by `"   "` — the same
    hole `test_whitespace_only_name_is_refused` found in Phase 1's add-hardware form.

    A reasonless body is malformed regardless of whether the item is held, so the
    refusals below stand on their own; the rental is arranged only so that the
    consequence assertions and the control have something to be about.
    """
    rented = user_client.post(rent_path(RENTABLE_ITEM))

    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "\t\n"}):
        response = admin_client.post(force_return_path(RENTABLE_ITEM), json=body)
        assert response.status_code in (400, 422), (
            f"a force-return with body {body!r} states no reason and must be refused "
            f"as malformed; got {response.status_code}: {response.text}"
        )

    assert rented.status_code in ACCEPTED, (
        f"the employee's rent must have succeeded for the two assertions below to "
        f"mean anything; it answered {rented.status_code}: {rented.text}"
    )

    assert len(_active(rental_rows(app, RENTABLE_ITEM))) == 1, (
        "no reasonless force-return may have ended the rental; got "
        f"{rental_rows(app, RENTABLE_ITEM)}"
    )
    assert statuses_by_id(admin_client)[RENTABLE_ITEM] == "In Use", (
        "the item is still held after every refused force-return"
    )

    allowed = admin_client.post(
        force_return_path(RENTABLE_ITEM), json={"reason": "Employee left the company"}
    )
    assert allowed.status_code in ACCEPTED, (
        "control failed: a force-return *with* a reason must work. Got "
        f"{allowed.status_code}: {allowed.text}"
    )


def test_non_admin_cannot_force_return(
    app,
    user_client: TestClient,
    other_user_client: TestClient,
    admin_client: TestClient,
) -> None:
    """Force-return is an admin verb, and holding the item does not confer it.

    Two callers, because they are refused for different reasons and both would be
    tempting to allow. A colleague force-returning somebody else's laptop is the
    escalation; the *renter* force-returning their own is the quiet one — it looks
    harmless, and it lets any employee write an `audit_events` row attributed to
    themselves, turning the admin-override trail into something anybody can post to.

    `403` and not `409`: these callers are being refused for who they are, not for the
    state of the item, and the Vue client renders those two differently. The role check
    runs before any of the item's state is consulted, so both refusals below stand
    whether or not the rental was successfully arranged.
    """
    rented = user_client.post(rent_path(RENTABLE_ITEM))
    body = {"reason": "I would like it back please"}

    colleague = other_user_client.post(force_return_path(RENTABLE_ITEM), json=body)
    assert colleague.status_code == 403, (
        "an employee who is not an admin must be refused force-return with 403; got "
        f"{colleague.status_code}: {colleague.text}"
    )

    renter = user_client.post(force_return_path(RENTABLE_ITEM), json=body)
    assert renter.status_code == 403, (
        "the renter is not an admin either — they have `return`, which needs no "
        "reason and writes no audit event. Letting them force-return lets any "
        f"employee author an admin-override record; got {renter.status_code}: "
        f"{renter.text}"
    )

    assert rented.status_code in ACCEPTED, (
        f"the employee's rent must have succeeded for the assertion below to mean "
        f"anything; it answered {rented.status_code}: {rented.text}"
    )
    assert len(_active(rental_rows(app, RENTABLE_ITEM))) == 1, (
        "neither refused force-return may have ended the rental; got "
        f"{rental_rows(app, RENTABLE_ITEM)}"
    )

    allowed = admin_client.post(force_return_path(RENTABLE_ITEM), json=body)
    assert allowed.status_code in ACCEPTED, (
        "control failed: an admin must be able to force-return. Got "
        f"{allowed.status_code}: {allowed.text}"
    )


def test_rental_routes_require_a_session(
    app, anonymous_client: TestClient, admin_client: TestClient
) -> None:
    """Nobody without a session moves any hardware, on any of the four new routes.

    ADR-0006 closed the anonymous read of the inventory; these are the anonymous
    *writes*, and they arrive with the same public URL. One test rather than four
    because it is one claim — no session, no effect — and splitting it into four
    near-identical bodies would make it likelier that the fifth route added later gets
    no test at all than that any of these four does.

    The inventory snapshot is compared before and after all four, so a route that
    refuses with the right code after already moving the item is still caught.
    """
    before = statuses_by_id(admin_client)
    paths = (
        rent_path(RENTABLE_ITEM),
        return_path(HELD_ITEM),
        force_return_path(HELD_ITEM),
        f"{HARDWARE_PATH}/6/clear-review",
    )

    for path in paths:
        response = anonymous_client.post(path, json={"reason": "no session here"})
        assert response.status_code in ANONYMOUS_REFUSAL, (
            f"a caller with no session must be refused at POST {path} — this is the "
            f"request a stranger with the deployed URL sends; got "
            f"{response.status_code}: {response.text}"
        )

    assert statuses_by_id(admin_client) == before, (
        "no anonymous request may have changed a status; got "
        f"{statuses_by_id(admin_client)} where {before} was expected"
    )
    assert not rental_rows(app, RENTABLE_ITEM), (
        "the anonymous rent must not have written a rental row; got "
        f"{rental_rows(app, RENTABLE_ITEM)}"
    )
    assert len(_active(rental_rows(app, HELD_ITEM))) == 1, (
        f"seed item {HELD_ITEM}'s rental must still be open after two anonymous "
        f"attempts to close it; got {rental_rows(app, HELD_ITEM)}"
    )
    assert items_by_id(admin_client)[6]["needs_review"] is True, (
        "the anonymous clear-review must not have cleared the flag on item 6"
    )


# --------------------------------------------------------------------------
# The seed's own rental (ADR-0007)
# --------------------------------------------------------------------------


def test_seed_id_7_imports_as_an_accountless_rental(
    app, admin_client: TestClient
) -> None:
    """Seed id 7 arrives as a real rental held by an address with no account.

    `j.doe@booksy.com` predates the account system and nobody can authenticate as
    them. ADR-0007 imports the row as the seed states it — `account_id = NULL`, the
    email snapshotted, `started_at` unknown-but-recorded — rather than releasing it
    the way ingestion released the orphan at seed id 2. The difference is that id 2
    named nobody, so the rental could not be reconstructed; id 7 names somebody, so it
    can.

    The last assertion is the discriminating one. An import that opens a rental for
    every `In Use`-looking row, or for every row at all, satisfies everything above
    while inventing history: id 2 was *released* at import and must have no rental,
    and no `Available` item may have one either.
    """
    rows = rental_rows(app, HELD_ITEM)
    assert len(rows) == 1, (
        f"seed item {HELD_ITEM} must import as exactly one rental row (ADR-0007); got "
        f"{len(rows)}: {rows}"
    )

    row = rows[0]
    absent = missing_columns(row, *RENTAL_COLUMNS)
    assert not absent, f"the rentals row is missing {absent}; got {sorted(row)}"

    assert row["account_id"] is None, (
        "the imported rental has no account behind it — nobody can authenticate as "
        f"{SEED_RENTER_EMAIL}, and inventing an account for them would be fabricating "
        f"an employee; got account_id={row['account_id']!r}"
    )
    assert row["renter_email"] == SEED_RENTER_EMAIL, (
        "the email is snapshotted verbatim from the seed, because it is the only "
        f"trace of who has the headphones; got {row['renter_email']!r}"
    )
    assert row["ended_at"] is None, (
        "the imported rental is active: the seed says the item is out, and NULL is "
        f"what active means; got ended_at={row['ended_at']!r}"
    )
    assert row["started_at"], (
        "`started_at` is unknown-but-recorded, not omitted — a NOT NULL column left "
        "empty would make the row unwritable and the rental would silently not exist"
    )
    assert statuses_by_id(admin_client)[HELD_ITEM] == "In Use", (
        "the item's own status must agree with the rental log at import, or the two "
        "start out already drifted (ADR-0007)"
    )

    held_ids = {row["item_id"] for row in rental_rows(app)}
    assert held_ids == {HELD_ITEM}, (
        "the seed produces exactly one rental. Seed id 2 was In Use with no assignee "
        "and ingestion *released* it, so a rental row for it would be invented "
        f"history; got rentals for items {sorted(held_ids)}"
    )


def test_the_seed_rental_can_be_ended_by_force_return(
    app, user_client: TestClient, admin_client: TestClient
) -> None:
    """The accountless rental is not a permanent write-off.

    ADR-0007 says seed id 7 is returnable only by force-return, since nobody can sign
    in as its holder. Left untested that sentence describes two possible products: one
    where an admin recalls the headphones, and one where a row imported on day zero
    makes an item unrentable forever — the same shape of dead end ADR-0003 spent a
    whole amendment closing for `needs_review`.

    `closed_by_email` is asserted because the rental's *renter* half stays NULL-backed
    forever; if the closer's half were filled in the same way, the one usable fact
    about this row — who took the decision to reclaim it — would be lost too.
    """
    response = admin_client.post(
        force_return_path(HELD_ITEM), json={"reason": "Holder is not an employee here"}
    )

    assert response.status_code in ACCEPTED, (
        f"an admin must be able to force-return the seed's accountless rental; got "
        f"{response.status_code}: {response.text}"
    )
    assert statuses_by_id(admin_client)[HELD_ITEM] == "Available", (
        f"item {HELD_ITEM} must be back in circulation; got "
        f"{statuses_by_id(admin_client)[HELD_ITEM]!r}"
    )

    rows = rental_rows(app, HELD_ITEM)
    assert len(rows) == 1, f"the imported rental is closed, not replaced; got {rows}"
    assert rows[0]["ended_at"], "the imported rental must be closed"
    assert rows[0]["close_kind"] == "force_return", (
        f"the only verb that could have closed it is force_return; got "
        f"{rows[0]['close_kind']!r}"
    )
    assert rows[0]["closed_by_email"] == ADMIN_EMAIL, (
        "the admin who reclaimed it is recorded, even though the renter never had an "
        f"account; got {rows[0]['closed_by_email']!r}"
    )

    reclaimed = user_client.post(rent_path(HELD_ITEM))
    assert reclaimed.status_code in ACCEPTED, (
        "an employee must be able to rent the headphones once they are back — "
        f"otherwise the seed's rental was a permanent write-off. Got "
        f"{reclaimed.status_code}: {reclaimed.text}"
    )
