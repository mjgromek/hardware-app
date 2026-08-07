"""Phase 4 — the three columns the UI needs, and the Add New Device fields.

Scope is the schema slice: `serial_number` (nullable text), `category` (a closed
enum, nullable) and `date_added` (now, on create). Every assertion here goes over
HTTP, so a column that does not exist yet fails the assertion that wanted it rather
than an import — the established pattern in `tests/conftest.py`.

**Two things the scope left open, pinned as loosely as the tests allow:**

- **How `date_added` is serialised.** "Backfilled from `purchase_date`" implies a
  date; "defaults to now on create" implies a timestamp. Nothing here reads the raw
  string: `_as_date` accepts either and every comparison is on the calendar day. An
  implementation is free to pick.
- **Seed id 10 has no `purchase_date` to backfill from.** There is no spec for what
  it gets, so `test_seed_item_without_a_purchase_date_still_lists`asserts only that
  the field is present and, if set, is a real date — the value itself is left for a
  human to decide. See the report.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import CREATED, HARDWARE_PATH, items_by_id, missing_columns, statuses_by_id

#: The closed set. A sixth value is not a new option, it is a bug (CONTEXT.md's
#: status enum is drawn the same way, and `PATCH /api/hardware/{id}` already
#: refuses off-enum statuses with a 422).
CATEGORIES = ("Laptop", "Mobile", "Tablet", "Monitor", "Accessory")

NEW_ITEM: dict[str, Any] = {
    "name": "Framework Laptop 13",
    "brand": "Framework",
    "purchase_date": "2026-03-01",
}

#: The seed row with no `purchase_date` at all — "Unknown Device", quarantined for
#: its off-enum status and imported flagged (ADR-0002). It is the only record whose
#: `date_added` cannot be derived.
UNDATED_SEED_ITEM = 10


def _as_date(value: Any) -> date:
    """A `date_added` off the wire, as a calendar day.

    Deliberately tolerant of both plausible serialisations. A test that demanded
    `"2021-11-23"` exactly would be pinning a decision the scope never made, and
    would go red against a perfectly correct timestamp column.
    """
    assert isinstance(value, str), f"date_added must serialise as a string; got {value!r}"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _create(client: TestClient, **fields: Any) -> dict[str, Any]:
    """Add an item and hand back the created row, failing loudly on setup."""
    response = client.post(HARDWARE_PATH, json={**NEW_ITEM, **fields})
    assert response.status_code in CREATED, (
        f"setup: an admin must be able to add {fields!r}; POST {HARDWARE_PATH} "
        f"returned {response.status_code}: {response.text}"
    )
    return response.json()


# ---------------------------------------------------------------------------
# The category enum is closed — the guard, before the happy path
# ---------------------------------------------------------------------------


def test_off_enum_category_is_refused(admin_client: TestClient) -> None:
    """A category outside the five is a 422, and nothing is written.

    The whole point of a closed dropdown is that the column can only ever hold values
    the UI knows how to render and the filter knows how to group by. A handler that
    accepts `"Desktop"` puts a category in the database that no screen will ever show
    and no filter will ever match — the item becomes invisible rather than wrong,
    which is worse.

    The inventory is re-read afterwards for the same reason
    `test_non_admin_cannot_add_hardware` does it: a handler that inserts and *then*
    validates passes a status-only assertion while having already grown the table.
    """
    before = statuses_by_id(admin_client)

    response = admin_client.post(HARDWARE_PATH, json={**NEW_ITEM, "category": "Desktop"})

    assert response.status_code == 422, (
        "a category outside the closed set must be refused with 422; got "
        f"{response.status_code}: {response.text}"
    )
    assert statuses_by_id(admin_client) == before, (
        "the refusal must leave no item behind; the inventory changed from "
        f"{sorted(before)} to {sorted(statuses_by_id(admin_client))}"
    )


def test_every_named_category_is_accepted(admin_client: TestClient) -> None:
    """All five named values go in and come back unchanged.

    The partner to the refusal above: closed means *exactly* these, and a validator
    built from a typo'd or short list would be invisible to a test that only checks
    that garbage is rejected. Asserted in one test because the claim is about the set,
    not about any one member of it.
    """
    stored: dict[str, str] = {}
    for category in CATEGORIES:
        created = _create(admin_client, name=f"{category} under test", category=category)
        stored[category] = created.get("category")

    assert stored == dict(zip(CATEGORIES, CATEGORIES)), (
        f"every value in the closed set must round-trip; got {stored}"
    )


# ---------------------------------------------------------------------------
# Add New Device carries the two new fields
# ---------------------------------------------------------------------------


def test_added_device_keeps_its_serial_number_and_category(admin_client: TestClient) -> None:
    """The two fields survive the trip into the inventory, not just the response body.

    Read back through `GET /api/hardware` rather than trusted from the POST: the
    response body is what the handler claims, the listing is what it actually stored.
    A serialiser that echoes the request while dropping the columns on insert is
    exactly the defect this separation catches.
    """
    created = _create(admin_client, serial_number="C02XK1VTJGH5", category="Laptop")

    listed = items_by_id(admin_client).get(created["id"])
    assert listed is not None, (
        f"the created item {created['id']} must appear in the inventory; "
        f"saw ids {sorted(items_by_id(admin_client))}"
    )

    absent = missing_columns(listed, "serial_number", "category")
    assert not absent, f"the listed item is missing {absent}; got {listed}"
    assert listed["serial_number"] == "C02XK1VTJGH5", (
        f"the serial number must be stored as given; got {listed['serial_number']!r}"
    )
    assert listed["category"] == "Laptop", (
        f"the category must be stored as given; got {listed['category']!r}"
    )


def test_serial_number_and_category_are_optional(admin_client: TestClient) -> None:
    """An item added without them is created, with both null.

    Both columns are nullable because the real inventory is: the seed's eleven rows
    have neither, and an admin holding a device with a rubbed-off label must still be
    able to add it. Required fields here would make the Add New Device form unusable
    for precisely the equipment most in need of recording.
    """
    created = _create(admin_client)

    listed = items_by_id(admin_client)[created["id"]]
    absent = missing_columns(listed, "serial_number", "category")
    assert not absent, f"the listed item is missing {absent}; got {listed}"
    assert listed["serial_number"] is None, (
        f"an unsupplied serial number must be null, not invented; got "
        f"{listed['serial_number']!r}"
    )
    assert listed["category"] is None, (
        f"an unsupplied category must be null, not defaulted into the enum; got "
        f"{listed['category']!r}"
    )


def test_a_newly_added_device_is_dated_now(admin_client: TestClient) -> None:
    """`date_added` is set by the server, on create, to today.

    Not taken from `purchase_date` — the two mean different things. A laptop bought in
    2021 and found in a drawer today entered the Hub today, and sorting the dashboard
    by "recently added" has to show it at the top or the column has no purpose.

    Compared with a day of slack so the test does not fail at a UTC midnight boundary,
    and never against a stored string: the claim is "roughly now", not a timestamp.
    """
    created = _create(admin_client, purchase_date="2021-11-23")

    absent = missing_columns(created, "date_added")
    assert not absent, f"a created item must carry {absent}; got {created}"

    added = _as_date(created["date_added"])
    today = datetime.now(timezone.utc).date()
    assert abs(added - today) <= timedelta(days=1), (
        f"a new item must be dated now, not from its purchase date; date_added was "
        f"{added} against today {today}"
    )


# ---------------------------------------------------------------------------
# The eleven seed records
# ---------------------------------------------------------------------------


def test_seed_items_have_no_serial_number_and_no_category(admin_client: TestClient) -> None:
    """Every seeded row carries both columns, both null.

    `data/seed.json` records neither, and the migration must not guess: a category
    inferred from a name would put "Razer Basilisk V2" under whatever the guesser
    thought a Basilisk was, and nobody downstream could tell an inference from a fact
    an admin typed in. Null is the honest value for information the Hub does not have.
    """
    items = items_by_id(admin_client)
    assert items, "setup: the seed must have loaded, or this test proves nothing"

    absent = {
        item_id: missing_columns(item, "serial_number", "category")
        for item_id, item in items.items()
    }
    assert not any(absent.values()), (
        f"seeded items are missing columns: { {k: v for k, v in absent.items() if v} }"
    )

    populated = {
        item_id: (item["serial_number"], item["category"])
        for item_id, item in items.items()
        if item["serial_number"] is not None or item["category"] is not None
    }
    assert not populated, (
        "the seed records neither field, so both must be null on every imported row; "
        f"these were set: {populated}"
    )


def test_seed_date_added_is_backfilled_from_purchase_date(admin_client: TestClient) -> None:
    """A seeded row that has a purchase date is dated from it.

    The eleven rows predate the column, so the only defensible value is the one date
    the record already carries. Backfilling them all to the day of the deploy would
    tell the dashboard that the entire inventory arrived at once, which is false and
    makes "recently added" meaningless for the only data the Hub actually has.

    Applied to *every* dated row, including seed id 6, whose purchase date is in the
    future and is quarantined for it (ADR-0002). The row is still imported with that
    date, and the rule is the rule; if id 6 should be special-cased, that is a spec
    decision and this assertion is where it will surface.
    """
    items = items_by_id(admin_client)
    dated = {
        item_id: item
        for item_id, item in items.items()
        if item.get("purchase_date") is not None
    }
    assert dated, "setup: the seed must import rows with purchase dates"

    absent = {item_id: missing_columns(item, "date_added") for item_id, item in dated.items()}
    assert not any(absent.values()), (
        f"seeded items are missing date_added: {sorted(k for k, v in absent.items() if v)}"
    )

    mismatched = {
        item_id: (item["purchase_date"], item["date_added"])
        for item_id, item in dated.items()
        if item["date_added"] is None
        or _as_date(item["date_added"]) != _as_date(item["purchase_date"])
    }
    assert not mismatched, (
        "each seeded row's date_added must be backfilled from its purchase_date; "
        f"these differ (purchase_date, date_added): {mismatched}"
    )


def test_seed_item_without_a_purchase_date_still_lists(admin_client: TestClient) -> None:
    """Seed id 10 has nothing to backfill from, and must not break the listing.

    **This test deliberately does not pin the value.** The scope says `date_added` is
    backfilled from `purchase_date` and that id 10 has none; null and "the day it was
    imported" are both defensible and choosing between them is a product decision, not
    a test author's. What is not negotiable is that the row survives with the column
    present and, if the migration did put something there, that it is a real date —
    a sentinel like `""` or `"unknown"` would break every consumer that parses it.
    """
    item = items_by_id(admin_client).get(UNDATED_SEED_ITEM)
    assert item is not None, (
        f"seed id {UNDATED_SEED_ITEM} is imported flagged, not dropped (ADR-0002); "
        "it must still appear in the inventory"
    )
    assert item["purchase_date"] is None, (
        "setup: this test is about the row with no purchase date; seed id "
        f"{UNDATED_SEED_ITEM} now has {item['purchase_date']!r}"
    )

    absent = missing_columns(item, "date_added")
    assert not absent, f"the undated row must still carry {absent}; got {item}"
    if item["date_added"] is not None:
        _as_date(item["date_added"])
