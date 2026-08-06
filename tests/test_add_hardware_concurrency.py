"""Phase 1 — two admins adding hardware at the same moment.

`mvp-reviewer` reproduced this: `add_item` read `max(id)` and then inserted, so six
concurrent `POST /api/hardware` calls raced and one crashed with
`sqlite3.IntegrityError: UNIQUE constraint failed: hardware.id`. The docstring called
`max(id) + 1` "the only value certain to be free", which is true for one caller and false
for two.

It is fixed in Phase 1 rather than filed, because Phase 2 is entirely about concurrency:
its `test_concurrent_rent_only_one_succeeds` asserts that two people cannot rent the same
laptop. A codebase that cannot survive two simultaneous inserts has no business making
that promise, and `app/storage.py`'s own docstring says the caller owns the transaction
precisely so the rental engine can hold one.

Also the whitespace-name defect from the same review: `Field(min_length=1)` accepted
`"   "`, which is exactly the unidentifiable row `test_added_hardware_requires_a_name`
exists to prevent — it only omitted the key, so a name made of spaces walked past it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tests.conftest import CREATED, HARDWARE_PATH, statuses_by_id

CONCURRENT_ADDS = 6


def test_concurrent_adds_all_succeed_with_distinct_ids(admin_client: TestClient) -> None:
    """Six simultaneous additions produce six items with six different ids.

    Both halves are the assertion. **No request may fail** — a `500` from an
    `IntegrityError` is the raw defect, and an admin seeing "Internal Server Error" after
    adding a laptop has no way to know whether it landed. **No id may repeat** — an
    `INSERT` that picked an id another transaction had just taken would either collide or,
    worse, overwrite that row, silently replacing a real device.

    The inventory count is checked last, because "six succeeded" and "six exist" are
    different claims: a handler that answered `201` while losing a row to a race satisfies
    the first and fails the second.
    """
    before = statuses_by_id(admin_client)

    def add(index: int):
        return admin_client.post(HARDWARE_PATH, json={"name": f"Concurrent Laptop {index}"})

    with ThreadPoolExecutor(max_workers=CONCURRENT_ADDS) as pool:
        responses = list(pool.map(add, range(CONCURRENT_ADDS)))

    failures = [(r.status_code, r.text[:160]) for r in responses if r.status_code not in CREATED]
    assert not failures, (
        f"every concurrent add must succeed; {len(failures)} of {CONCURRENT_ADDS} failed. "
        "A UNIQUE constraint error here means the id was chosen by a SELECT that another "
        f"transaction had already acted on. Failures: {failures}"
    )

    new_ids = [r.json()["id"] for r in responses]
    assert len(set(new_ids)) == CONCURRENT_ADDS, (
        f"each add must get its own id; got {sorted(new_ids)}. A repeated id means one "
        "insert overwrote another item"
    )
    assert not set(new_ids) & set(before), (
        f"no new id may reuse an existing one; {sorted(set(new_ids) & set(before))} were "
        "already in the inventory"
    )

    after = statuses_by_id(admin_client)
    assert len(after) == len(before) + CONCURRENT_ADDS, (
        f"all {CONCURRENT_ADDS} items must be in the inventory afterwards; it went from "
        f"{len(before)} to {len(after)}"
    )


def test_whitespace_only_name_is_refused(admin_client: TestClient) -> None:
    """A name of spaces is not a name.

    `min_length=1` is satisfied by `"   "`, which reaches the database and renders as a
    blank row in the dashboard — indistinguishable from a rendering bug, and precisely the
    "row a human cannot identify" that record 10 of the seed exists to demonstrate.

    The trailing assertion is the one with teeth: the refusal must not have written
    anything. And a name with real content surrounded by spaces is *not* an error — it is
    trimmed, because the alternative is an item whose name sorts and searches strangely
    for a reason nobody can see.
    """
    before = statuses_by_id(admin_client)

    for blank in ("   ", "\t", "\n", ""):
        response = admin_client.post(HARDWARE_PATH, json={"name": blank})
        assert response.status_code in (400, 422), (
            f"a name of {blank!r} must be refused — it satisfies min_length but names "
            f"nothing; got {response.status_code}: {response.text[:160]}"
        )

    assert statuses_by_id(admin_client) == before, (
        "no refused name may have added a row to the inventory"
    )

    padded = admin_client.post(HARDWARE_PATH, json={"name": "  Framework Laptop 13  "})
    assert padded.status_code in CREATED, (
        f"a name with content must still be accepted; got {padded.status_code}"
    )
    assert padded.json()["name"] == "Framework Laptop 13", (
        "surrounding whitespace must be trimmed rather than stored — an item whose name "
        f"begins with a space sorts and searches oddly for an invisible reason; got "
        f"{padded.json()['name']!r}"
    )
