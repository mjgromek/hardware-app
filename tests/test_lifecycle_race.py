"""A rent racing an account deletion — the named blind-spot bet, pinned.

The class this suite was missing was never security, it was entity lifecycle: a
recycled rowid produced full admin takeover under 91 green tests (ADR-0013). The
grilling named the likely next member — a lifecycle transition racing a concurrent
consumer — and this file is the answer to "so why are we talking instead of you
testing it?"

The shape is ADR-0008's, one layer up. The delete route *reads* "this account holds
nothing", then *writes* the soft delete. A rent committed between the read and the
write strands an active rental on a deleted account: the renter can no longer sign in
to return it, and "no active rental outlives its owner" — the invariant ADR-0013 calls
what makes an inherited rental unreachable — is broken. A read-then-write cannot win a
race; the write has to come first, so the read runs behind SQLite's single-writer lock.

The interleave is driven deterministically rather than with a thread storm: the
rentals read inside the delete request is wrapped so that a racing rent commits on a
second connection at the worst possible moment — after the read, before the delete's
write. Under the unfixed ordering that rent lands cleanly and the test goes red; under
the fixed ordering the delete's write already holds the lock, so the racing commit is
refused and the invariant holds. Either outcome of the race is acceptable — delete
refused with 409, or rent refused — what may never happen is both succeeding.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import rentals as rentals_module
from app.accounts import find_by_id
from app.rentals import rent
from tests.conftest import USER_EMAIL, accounts_by_email

#: Seed id 1: `Available`, unflagged, and nobody's.
CONTESTED_ITEM = 1


def _users_row(app, account_id: int) -> dict[str, Any]:
    engine = app.state.engine
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT id, deleted_at FROM users WHERE id = :id"), {"id": account_id}
        ).mappings().one()
    return dict(row)


def _active_rentals_for(app, account_id: int) -> list[dict[str, Any]]:
    engine = app.state.engine
    if "rentals" not in inspect(engine).get_table_names():
        return []
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, item_id FROM rentals "
                "WHERE account_id = :id AND ended_at IS NULL"
            ),
            {"id": account_id},
        ).mappings().all()
    return [dict(row) for row in rows]


def test_rent_racing_deletion_cannot_strand_a_rental(
    app, database_path, admin_client, user_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rent landing inside the delete request must lose to it, or beat it — not both.

    Three acceptable worlds after the dust settles:
    - the rent was refused (the delete's write already held the lock) and the account
      is gone;
    - the delete answered ``409`` (the guard saw the rental) and the account survives
      with its rental;
    - nobody crashed.

    The unacceptable world is the one the unfixed ordering produces: ``204``, a
    soft-deleted account, and an active rental it can never return.
    """
    account_id = accounts_by_email(admin_client)[USER_EMAIL]["id"]

    # The racing writer gets its own connection over the same file, with a busy
    # timeout short enough that "refused by the lock" is a fast, observed outcome
    # rather than a five-second stall.
    racing_engine = create_engine(
        f"sqlite:///{database_path}", connect_args={"timeout": 0.2}
    )

    real_read = rentals_module.item_ids_held_by
    race: dict[str, Any] = {"outcome": "never ran"}

    def read_then_lose_the_race(session: Session, target_id: int) -> set[int]:
        ids = real_read(session, target_id)
        if target_id != account_id or race["outcome"] != "never ran":
            return ids
        # The worst moment: the delete route has read "holds nothing" and has not
        # yet acted on it. A colleague rents on another connection right now.
        try:
            with Session(racing_engine) as racing_session:
                renter = find_by_id(racing_session, target_id)
                assert renter is not None, "setup: the account must be live to rent"
                rent(racing_session, CONTESTED_ITEM, renter)
                racing_session.commit()
            race["outcome"] = "committed"
        except OperationalError:
            # The delete's write already holds SQLite's lock — the race is lost
            # by the rent, which is one of the two acceptable outcomes.
            race["outcome"] = "refused by the lock"
        return ids

    monkeypatch.setattr(rentals_module, "item_ids_held_by", read_then_lose_the_race)

    response = admin_client.delete(f"/api/users/{account_id}")

    assert race["outcome"] != "never ran", (
        "setup: the racing rent must actually have been attempted inside the "
        "delete request, or this test raced nothing"
    )
    assert response.status_code < 500, (
        "neither party to the race may receive a 5xx — a 'database is locked' "
        "escaping as an Internal Server Error is the race lost by the application "
        f"and caught by the driver; got {response.status_code}: {response.text[:200]}"
    )
    assert response.status_code in (204, 409), (
        f"the delete either succeeds or is refused as a conflict; got "
        f"{response.status_code}: {response.text[:200]}"
    )

    deleted = _users_row(app, account_id)["deleted_at"] is not None
    stranded = _active_rentals_for(app, account_id)

    assert not (deleted and stranded), (
        "an account was soft-deleted while holding an active rental — the renter "
        "cannot sign in to return it, and ADR-0013's 'no active rental outlives its "
        f"owner' is broken. Race outcome: {race['outcome']!r}; delete answered "
        f"{response.status_code}; stranded rentals: {stranded}"
    )
    if response.status_code == 204:
        assert deleted and not stranded, (
            "a 204 must mean the account is gone and holds nothing; got "
            f"deleted={deleted}, rentals={stranded}, race={race['outcome']!r}"
        )
    else:
        assert not deleted, (
            "a 409 must leave the account exactly as it was — refused means "
            f"refused; got deleted={deleted}, race={race['outcome']!r}"
        )
