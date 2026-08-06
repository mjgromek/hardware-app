"""Application factory.

Single origin (ADR-0001): this one FastAPI app serves both the API and the built
Vue bundle from ``dist/``. There is no CORS configuration because there is no
cross-origin request to configure.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Mapping

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints

from app import accounts, audit, guards, rentals, sessions
from app.config import PRODUCTION, load_settings
from app.domain import Account, Role, Status
from app.storage import (
    add_item,
    clear_review,
    create_engine_for,
    create_schema,
    delete_item,
    load_items,
    new_session,
    set_status,
)

#: The built Vue bundle. Absent until the frontend has been built, which is why
#: the mount is conditional rather than assumed.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

#: One body for every refused login. Wrong password and unknown address get the
#: same bytes, or the endpoint enumerates accounts for anyone willing to ask twice —
#: which matters here because the deployment publishes demo credentials (ADR-0005),
#: making the login form the one route a stranger is certain to reach.
INVALID_CREDENTIALS = "Invalid email or password"


class Credentials(BaseModel):
    email: str
    password: str


class NewAccount(BaseModel):
    email: str
    password: str
    role: Role


class RoleChange(BaseModel):
    role: Role


class NewHardware(BaseModel):
    """What an admin can tell us about a device they are holding.

    `name` is required and the rest are not, which mirrors the seed: real rows arrive
    with a missing brand or no purchase date (id 10 has neither), and refusing those
    fields here would make the API stricter than the data it already stores.
    """

    #: Trimmed before length is checked, so `"   "` is refused rather than stored. A name
    #: made of spaces satisfies `min_length=1`, reaches the database, and renders as a
    #: blank dashboard row — indistinguishable from a rendering bug, and exactly the
    #: unidentifiable record the seed's row 10 exists to demonstrate.
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    brand: str | None = None
    purchase_date: date | None = None


class StatusChange(BaseModel):
    status: Status


class Reason(BaseModel):
    """The mandatory reason on every admin override (ADR-0010).

    Trimmed before length is checked, for the same reason a hardware name is: a reason
    of spaces satisfies `min_length` and records nothing.
    """

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


#: Serialised for admins only (ADR-0012). Maintenance prose written for an auditor —
#: Phase 3 writes findings into the same columns. Renter identity is *not* here: who
#: holds a laptop is operational, and hiding it moves the question to Slack.
ADMIN_ONLY_FIELDS = ("notes", "history", "review_reason")


def visible_to(item: dict[str, Any], account: Account) -> dict[str, Any]:
    """One item, as this caller is allowed to see it.

    The restricted fields are set to `None` rather than dropped, so the payload keeps
    one shape and the client does not have to branch on which role it is.
    """
    if account.role is Role.ADMIN:
        return item
    return {
        key: (None if key in ADMIN_ONLY_FIELDS else value) for key, value in item.items()
    }


class HeldBy(str, Enum):
    """The only accepted value of `?held_by`. Closed, like `Status` and `SortKey`.

    An open parameter taking an email would let any signed-in employee enumerate what a
    named colleague is holding. That is a different feature with a different
    authorization question, and Phase 2 has not asked it.
    """

    ME = "me"


class SortKey(str, Enum):
    """The columns the dashboard may sort on. Closed, so an unknown key is a `422`.

    One member today. It is an enum rather than a bare string because the difference
    between "unrecognised sort key" and "no sort key" must not be invisible: silently
    returning unsorted rows for a typo is the kind of bug a user reports as "sorting
    doesn't work sometimes".
    """

    PURCHASE_DATE = "purchase_date"


#: Named once, because Phase 2 adds four routes under it.
HARDWARE = "/api/hardware"


def _claim(transition):
    """Run a transition, turning its `GuardViolation` into `409` with the reason kept.

    Same translation as `_enforce`, for the case where the refusal comes out of the
    atomic write rather than a pre-check (ADR-0008).
    """
    try:
        return transition()
    except guards.GuardViolation as violation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(violation))


def _enforce(guard, *args, **kwargs) -> None:
    """Run a guard, translating its violation into `409` with the reason intact.

    The translation lives here, once, so guards stay ignorant of HTTP and every route
    answers a violated invariant with the same status and a readable message
    (CONTEXT.md). ADR-0005's `409` and ADR-0003's `409` come through this one line.
    """
    try:
        guard(*args, **kwargs)
    except guards.GuardViolation as violation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(violation))


def create_app(env: Mapping[str, str] | None = None) -> FastAPI:
    """Build the application, or refuse to boot.

    Loads settings first, so a production environment missing ``ADMIN_PASSWORD``
    fails here rather than at first request (ADR-0005).
    """
    settings = load_settings(os.environ if env is None else env)

    # Under uvicorn the root logger has no handler, so application logs vanish
    # even though they are emitted. `caplog` captures propagated records, so tests
    # pass either way — this is what makes the boot-seed line visible in a real
    # deployment. `force=False` leaves an already-configured host alone.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s"
    )

    app = FastAPI(title="Hardware Hub")
    app.state.settings = settings

    # Once per process, not once per request (see app/storage.py).
    engine = create_engine_for(settings.database_url)
    create_schema(engine)
    app.state.engine = engine

    # Deploy shim, guarded by emptiness: a fresh volume gets the seed, a database
    # with anything in it is left alone. Imported here rather than at module level
    # so `app` does not depend on `scripts` just to be importable. See BACKLOG.md.
    # Before the seed: `seed_if_empty` opens the rentals ADR-0007 describes, and DDL
    # cannot run on a second connection while that session holds a write transaction.
    rentals.create_schema(engine)
    audit.create_schema(engine)

    from scripts.seed import seed_if_empty

    seed_if_empty(engine)

    # Every boot, not only an empty one. A volume seeded before Phase 2 has items that
    # are `In Use` with a holder and no rental row — unreturnable and unrecallable —
    # and `seed_if_empty` will never run again to fix them. Idempotent, so a restart
    # over a reconciled database does nothing.
    with new_session(engine) as session:
        reconciled = rentals.reconcile_held_items(session, load_items(session))
        session.commit()
    if reconciled:
        logging.getLogger(__name__).info(
            "reconciled %d held item(s) that had no rental record", reconciled
        )

    # Admin #1 comes from the environment, not from a migration (ADR-0005). Done at
    # boot for the same reason the seed is: the deploy target offers no way to run a
    # one-off command against the mounted volume. Unlike the seed this is idempotent
    # and additive — it never overwrites an existing admin.
    accounts.create_schema(engine)
    with new_session(engine) as session:
        # Read before writing: `bootstrap_admin` is about to make the table non-empty,
        # and the demo account is created only on a database that never had an account.
        fresh = accounts.has_no_accounts(session)
        created = accounts.bootstrap_admin(
            session, settings.admin_email, settings.admin_password
        )
        # A replaced volume must not leave the README publishing credentials that no
        # longer exist — a reviewer meeting a login screen that rejects the only password
        # they have is the worst first impression this project can make. Guarded by
        # emptiness like the hardware seed, so a deliberately deleted demo account stays
        # deleted and a rotated password stays rotated.
        demo = (
            accounts.bootstrap_demo(session, settings.demo_email, settings.demo_password)
            if fresh
            else None
        )
        session.commit()

    log = logging.getLogger(__name__)
    if created is not None:
        log.info("bootstrapped admin #1 from the environment: %s", created.email)
    if demo is not None:
        log.info("created the published read-only demo account: %s", demo.email)

    # ------------------------------------------------------------------
    # The enforcement point (brainstorm.md §7, settled here)
    # ------------------------------------------------------------------
    #
    # Per-route dependencies, not middleware. Middleware sees every request
    # including the ones the static mount serves, so a global "refuse without a
    # session" would take the login page down with it — and
    # `test_serves_built_bundle_at_root` fetches `/` unauthenticated, so that shape
    # turns a passing test red rather than shipping. A dependency also puts the
    # requirement in the signature of the route it protects, where a reader looking
    # at the handler can see it.

    def current_account(request: Request) -> Account:
        """The account behind this request, or `401`.

        `401` and not `403`: this is what the dashboard's first fetch gets when
        nobody is signed in, and the Vue client reads the status to decide between
        the login screen and an error page. A `403` there is a dead end for someone
        who only needs to log in.

        The cookie is verified *and* the account re-read, so a session naming an
        account that has since been deleted is refused rather than trusted — the
        signature proves the id was not tampered with, not that it still exists.
        """
        account_id = sessions.subject_of(
            request.cookies.get(sessions.COOKIE_NAME), settings.secret_key
        )
        if account_id is not None:
            with new_session(engine) as session:
                account = accounts.find_by_id(session, account_id)
            if account is not None:
                return account
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue"
        )

    def current_admin(account: Account = Depends(current_account)) -> Account:
        """The account behind this request if it is an admin, or `403`.

        Layered on `current_account` so an anonymous caller still gets `401` and an
        authenticated non-admin gets `403`. The distinction is not cosmetic: showing
        a login form to somebody who is already signed in tells them the wrong thing
        about why they were refused.
        """
        if account.role is not Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action is for admins",
            )
        return account

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    @app.post("/api/login")
    def log_in(credentials: Credentials, response: Response) -> dict[str, Any]:
        """Exchange a credential for a session cookie, or refuse identically.

        The refusal is one shared body (`INVALID_CREDENTIALS`) and never echoes the
        submitted address: a reflected value is a hint to an attacker and an
        injection surface in whatever renders it.
        """
        with new_session(engine) as session:
            account = accounts.verify_credentials(
                session, credentials.email, credentials.password
            )

        if account is None:
            # Raised rather than returned, so no `Set-Cookie` can be attached to it
            # by a later line: a 401 that arrives with a session is worse than a 200.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS
            )

        response.set_cookie(
            sessions.COOKIE_NAME,
            sessions.issue(account.id, settings.secret_key),
            **sessions.cookie_kwargs(production=settings.environment == PRODUCTION),
        )
        return {"email": account.email, "role": account.role.value}

    @app.get("/api/session")
    def read_session(account: Account = Depends(current_account)) -> dict[str, Any]:
        """Who the caller is, for a client that holds an `HttpOnly` cookie.

        The cookie is unreadable from JavaScript by design, so after a reload the app
        knows it has *a* session and nothing about whose. This is the route it asks,
        and the `401` for an absent session is what turns into the login screen.

        Returns the `Account`, which has no field for a password digest.
        """
        return asdict(account)

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    @app.get("/api/users")
    def list_users(_: Account = Depends(current_admin)) -> list[dict[str, Any]]:
        """Every account, for the admin who manages them.

        Returns `id`, `email` and `role` — the whole of `Account`, which is a type
        that cannot hold a password digest, so this route cannot leak one.
        """
        with new_session(engine) as session:
            return [asdict(account) for account in accounts.list_accounts(session)]

    @app.post("/api/users", status_code=status.HTTP_201_CREATED)
    def create_user(
        new_account: NewAccount, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Create an account. Admin-only, because there is no self-registration.

        The guard runs before anything is written — `current_admin` is resolved
        before the body of this function exists — so a refused request cannot leave
        a usable account behind. That ordering is the property
        `test_non_admin_cannot_create_user` checks by trying to log in afterwards,
        rather than by trusting the status code.

        `role` is a `Role`, so an off-enum value is a `422` from the model and never
        reaches the database.
        """
        with new_session(engine) as session:
            try:
                account = accounts.create_account(
                    session,
                    new_account.email,
                    new_account.password,
                    new_account.role,
                )
            except accounts.EmailAlreadyExists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account already exists for that address",
                )
            session.commit()
        return asdict(account)

    @app.patch("/api/users/{account_id}")
    def change_role(
        account_id: int, change: RoleChange, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Promote or demote an account, unless it would empty the admin role."""
        with new_session(engine) as session:
            if accounts.find_by_id(session, account_id) is None:
                raise HTTPException(status_code=404, detail="No such account")
            _enforce(guards.ensure_an_admin_remains, session, account_id, becoming=change.role)
            accounts.set_role(session, account_id, change.role)
            session.commit()
            return asdict(accounts.find_by_id(session, account_id))

    @app.delete("/api/users/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_user(account_id: int, _: Account = Depends(current_admin)) -> Response:
        """Remove an account, unless it is the last admin (ADR-0005)."""
        with new_session(engine) as session:
            if accounts.find_by_id(session, account_id) is None:
                raise HTTPException(status_code=404, detail="No such account")
            _enforce(guards.ensure_an_admin_remains, session, account_id)
            accounts.delete_account(session, account_id)
            session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------

    @app.get("/api/hardware")
    def list_hardware(
        account: Account = Depends(current_account),
        status: Status | None = None,
        sort: SortKey | None = None,
        held_by: HeldBy | None = None,
    ) -> list[dict[str, Any]]:
        """The inventory, for a signed-in caller. Eleven rows needs no paging.

        Behind a session since ADR-0006: whole items carry `notes` and `history`,
        which are internal maintenance records and were public through Phase 0.

        **Both query parameters are typed, and that is the design.** `status` is a
        `Status`, so the seed's own off-enum `"Unknown"` is a `422` from FastAPI
        rather than a filter the handler silently drops — the failure mode where an
        admin filters for a status that does not exist, gets the entire inventory
        back, and reads it as "everything matches". `sort` is a closed set for the
        same reason: an unrecognised sort key must not quietly return unsorted rows.
        """
        with new_session(engine) as session:
            items = load_items(
                session,
                status=status,
                sort_by_purchase_date=sort is SortKey.PURCHASE_DATE,
            )
            if held_by is HeldBy.ME:
                # Scoped by *account*, not by "is it In Use" — the second renter is
                # what makes that difference visible, and getting it wrong hands one
                # employee's rentals to another. Seed id 7 has no account and so
                # belongs to nobody's list (ADR-0007).
                mine = rentals.item_ids_held_by(session, account.id)
                items = tuple(item for item in items if item.id in mine)
        return [visible_to(asdict(item), account) for item in items]

    @app.post("/api/hardware", status_code=status.HTTP_201_CREATED)
    def add_hardware(
        new_item: NewHardware, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Add an item to the inventory. Admin-only.

        `status` and `needs_review` are not accepted from the caller — see
        `storage.add_item`. The only fields an admin supplies are the ones they can
        read off the device in their hands.
        """
        with new_session(engine) as session:
            item = add_item(
                session,
                name=new_item.name,
                brand=new_item.brand,
                purchase_date=new_item.purchase_date,
            )
            session.commit()
        return asdict(item)

    @app.patch("/api/hardware/{item_id}")
    def change_status(
        item_id: int, change: StatusChange, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Move one item's status — the Repair toggle, in both directions.

        `StatusChange.status` is a `Status`, so an off-enum value is a `422` and never
        reaches the database. A fourth status in that column would break every guard
        that pattern-matches on the three (CONTEXT.md).
        """
        with new_session(engine) as session:
            item = _item_or_404(session, item_id)
            if change.status is Status.REPAIR:
                # CONTEXT.md names "a rented item in Repair" an impossible state, and
                # Phase 1 shipped the route that reached it (ADR-0009).
                _enforce(
                    guards.ensure_no_active_rental,
                    rentals.active_rental(session, item_id),
                    item,
                    "sent to Repair",
                )
            set_status(session, item_id, change.status)
            session.commit()
        return {"id": item_id, "status": change.status.value}

    @app.delete("/api/hardware/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    def remove_hardware(item_id: int, _: Account = Depends(current_admin)) -> Response:
        """Retire an item from the inventory. Admin-only."""
        with new_session(engine) as session:
            item = _item_or_404(session, item_id)
            _enforce(
                guards.ensure_no_active_rental,
                rentals.active_rental(session, item_id),
                item,
                "deleted",
            )
            delete_item(session, item_id)
            session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # Rentals — the transitions live in app/rentals.py (ADR-0008)
    # ------------------------------------------------------------------

    def _item_or_404(session, item_id: int):
        for item in load_items(session):
            if item.id == item_id:
                return item
        raise HTTPException(status_code=404, detail="No such hardware item")

    @app.post(f"{HARDWARE}/{{item_id}}/rent")
    def rent_hardware(
        item_id: int, account: Account = Depends(current_account)
    ) -> dict[str, Any]:
        """Claim an item. Any signed-in account may rent; the guards decide which item.

        The pre-check runs for the message and the atomic `UPDATE` makes the decision
        (ADR-0008), so a caller who passes the first and loses the second is told the
        item is in use — which by then it is.
        """
        with new_session(engine) as session:
            try:
                rental = rentals.rent(session, item_id, account)
            except guards.GuardViolation:
                # The claim failed. Only *now* read the row, to say why — reading first
                # would open a transaction the UPDATE then has to upgrade, and six
                # concurrent claimants upgrading one SQLite read lock deadlock rather
                # than serialise. Attempting the write first is both faster and the
                # honest ordering: the atomic statement is the decision (ADR-0008), and
                # the guards exist for the message.
                session.rollback()
                item = _item_or_404(session, item_id)
                _enforce(guards.ensure_item_is_rentable, item)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{item.name} is already in use — somebody else has it.",
                )
            session.commit()
        return {"item_id": item_id, "rental_id": rental.id, "renter": account.email}

    @app.post(f"{HARDWARE}/{{item_id}}/return")
    def return_hardware(
        item_id: int, account: Account = Depends(current_account)
    ) -> dict[str, Any]:
        """Close your own rental. Somebody else's is a `409` (ADR-0009)."""
        with new_session(engine) as session:
            _item_or_404(session, item_id)
            rental = _claim(lambda: rentals.return_(session, item_id, account))
            session.commit()
        return {"item_id": item_id, "rental_id": rental.id, "close_kind": "return"}

    @app.post(f"{HARDWARE}/{{item_id}}/force-return")
    def force_return_hardware(
        item_id: int, body: Reason, admin: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Recall an item from whoever holds it. Admin-only, reason mandatory.

        Writes an `audit_events` row in the same transaction as the close: a rental
        that ends without a record of who ended it is the audit trail becoming fiction
        (ADR-0010).
        """
        with new_session(engine) as session:
            _item_or_404(session, item_id)
            rental = _claim(
                lambda: rentals.force_return(session, item_id, admin, body.reason)
            )
            audit.record(
                session,
                actor=admin,
                action=audit.Action.FORCE_RETURN,
                reason=body.reason,
                item_id=item_id,
                rental_id=rental.id,
            )
            session.commit()
        return {"item_id": item_id, "rental_id": rental.id, "close_kind": "force_return"}

    @app.post(f"{HARDWARE}/{{item_id}}/clear-review")
    def clear_review_flag(
        item_id: int, body: Reason, admin: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Release an item from `needs_review`. Admin-only, reason mandatory.

        Allowed whatever the item's status — the flag and the status are orthogonal,
        which is why the dashboard gives the flag its own column rather than a fourth
        chip. `409` when nothing is flagged, because idempotency would hide a UI bug
        *and* file a mandatory reason against a non-event (ADR-0010).

        The reason goes with the flag: a cleared item still showing "purchase date is
        in the future" explains a restriction that no longer applies.
        """
        with new_session(engine) as session:
            item = _item_or_404(session, item_id)
            if not item.needs_review:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{item.name} is not flagged for review, so there is "
                    "nothing to clear.",
                )
            clear_review(session, item_id)
            audit.record(
                session,
                actor=admin,
                action=audit.Action.CLEAR_REVIEW_FLAG,
                reason=body.reason,
                item_id=item_id,
            )
            session.commit()
        return {"item_id": item_id, "needs_review": False}

    # Single origin (ADR-0001): the same app serves the API and the bundle, so
    # there is no CORS middleware to configure. Mounted last, at the root, so it
    # never shadows an API route.
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend"
        )

    return app
