"""Phase 1 — the dashboard's sort and filter, over the real seed.

Both tests run as a logged-in **`user`**, not an admin. The dashboard is what a
regular employee sees, so a mutation that quietly restricted sort or filter to admins
would otherwise go unnoticed until someone clicked through the deployed instance. The
inventory now requires a session at all — only admin-created accounts use the Hub —
which is pinned once, in ``test_auth.py::test_inventory_requires_a_session``, and not
re-litigated here.

The cost is visible and accepted: until ``POST /api/login`` exists these two report as
errors in fixture setup rather than as failures on sort and filter. An earlier draft
read the endpoint anonymously to avoid that, which was the wrong trade — it made the
red state prettier by testing a contract the product does not have.

Nothing here hardcodes a row count or an id list from `data/seed.json`. Expectations
are derived from the unfiltered response and compared against the filtered one, so
these tests still mean what they say if ingestion changes — and they compare like
with like, rather than pinning today's import behaviour a second time in a place
nobody would think to update. What is pinned is that the *derived* expectation is
non-trivial: a filter tested against zero matching rows proves nothing.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from tests.conftest import HARDWARE_PATH

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def test_dashboard_sorts_by_purchase_date(user_client: TestClient) -> None:
    """`?sort=purchase_date` orders the inventory oldest first, and keeps every row.

    Three separate properties, because they fail for different reasons.

    *Order* — the non-null dates come back non-decreasing. Only the non-null ones:
    where a missing date sorts is genuinely unspecified (see `BACKLOG.md`), and
    inventing an answer here would pin a decision nobody has made.

    *Completeness* — sorting is a permutation. Every id that came back unsorted has
    to come back sorted, or the dashboard silently hides inventory whenever someone
    clicks a column header. The re-keyed duplicate and the flagged rows are in that
    set, which is exactly the material a sort implemented as a filtered query drops.

    *Survival of the null date* — seed id 10 has ``purchaseDate: null``, and
    ``sorted(key=...)`` over ``None`` raises ``TypeError``. So the most likely
    failure of this endpoint is not a wrong order, it is a 500 on the one row the
    seed put there to be awkward. Asserting the response is 200 *and* that the
    undated item is present is what catches it.
    """
    unsorted = user_client.get(HARDWARE_PATH)
    assert unsorted.status_code == 200, (
        f"setup: the inventory must be readable; got {unsorted.status_code}"
    )
    expected_ids = sorted(item["id"] for item in unsorted.json())
    undated_ids = [
        item["id"] for item in unsorted.json() if item["purchase_date"] is None
    ]
    assert undated_ids, (
        "setup: the seed carries an item with no purchase date (id 10), and it is "
        "the row a naive sort key crashes on; without it this test cannot catch "
        "that"
    )

    response = user_client.get(HARDWARE_PATH, params={"sort": "purchase_date"})

    assert response.status_code == 200, (
        f"GET {HARDWARE_PATH}?sort=purchase_date must sort the inventory, not fail. "
        f"Got {response.status_code}: {response.text}. A sort key over a null "
        "purchase date raises TypeError, and the seed has one"
    )

    items = response.json()
    assert sorted(item["id"] for item in items) == expected_ids, (
        "sorting is a permutation: every item must still be there. Sorted response "
        f"held ids {sorted(item['id'] for item in items)}, the unsorted inventory "
        f"held {expected_ids}"
    )
    for item_id in undated_ids:
        assert item_id in {item["id"] for item in items}, (
            f"item {item_id} has no purchase date and was dropped from the sorted "
            "response — an item with a missing field must still appear in the "
            "dashboard, whichever end of the order it lands on"
        )

    dates = [
        item["purchase_date"] for item in items if item["purchase_date"] is not None
    ]
    assert all(ISO_DATE.match(value) for value in dates), (
        "purchase dates must serialise as ISO YYYY-MM-DD — the comparison below is "
        "only chronological if they do, and the dashboard sorts on what it is sent; "
        f"got {dates}"
    )
    assert dates == sorted(dates), (
        "the dated items must come back oldest first; got "
        f"{dates}, expected {sorted(dates)}"
    )


def test_dashboard_filters_by_status(user_client: TestClient) -> None:
    """`?status=` returns exactly the items with that status, and nothing else.

    Two statuses, not one, because a filter that hardcodes ``Repair`` — or that
    returns everything and lets the client sort it out — passes a single-status
    test. ``Repair`` and ``In Use`` are both drawn from the seed and both non-empty
    after ingestion (two items in ``Repair``: seed id 3 and the re-keyed duplicate;
    one ``In Use``: seed id 7, the only one that named an assignee).

    The last act is the one worth having. The seed's own off-enum value,
    ``"Unknown"``, is not a status (CONTEXT.md) — and the natural way to write this
    endpoint, ``if status: query = query.where(...)``, answers an unrecognised value
    by returning **the whole inventory**. That is the failure that looks like
    success: an admin filters for a status that does not exist, sees every item, and
    concludes every item matches. Either refuse it or return nothing; silently
    ignoring the filter is what must not happen.
    """
    everything = user_client.get(HARDWARE_PATH)
    assert everything.status_code == 200, (
        f"setup: the inventory must be readable; got {everything.status_code}"
    )
    inventory = everything.json()

    for status in ("Repair", "In Use"):
        expected = {item["id"] for item in inventory if item["status"] == status}
        assert expected, (
            f"setup: no imported item has status {status!r}, so filtering on it "
            "would pass against an endpoint that returns an empty list for "
            "everything"
        )

        response = user_client.get(HARDWARE_PATH, params={"status": status})

        assert response.status_code == 200, (
            f"GET {HARDWARE_PATH}?status={status} must filter the inventory; got "
            f"{response.status_code}: {response.text}"
        )
        returned = response.json()
        assert {item["id"] for item in returned} == expected, (
            f"filtering by {status!r} must return exactly the items with that "
            f"status: expected ids {sorted(expected)}, got "
            f"{sorted(item['id'] for item in returned)} out of "
            f"{len(inventory)} items"
        )
        assert all(item["status"] == status for item in returned), (
            f"every returned item must actually hold status {status!r}; got "
            f"{sorted({item['status'] for item in returned})}"
        )

    off_enum = user_client.get(HARDWARE_PATH, params={"status": "Unknown"})
    ignored_the_filter = (
        off_enum.status_code == 200 and len(off_enum.json()) == len(inventory)
    )
    assert not ignored_the_filter, (
        "an off-enum status must be refused (400/422) or match nothing — the seed's "
        "own 'Unknown' is not a status, and returning the entire inventory for it "
        "reads as 'everything matches' to whoever filtered. Got "
        f"{off_enum.status_code} with all {len(inventory)} items"
    )
