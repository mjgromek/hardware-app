"""Application factory.

Single origin (ADR-0001): this one FastAPI app serves both the API and the built
Vue bundle from ``dist/``. There is no CORS configuration because there is no
cross-origin request to configure.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints, field_validator

from app import accounts, ai, audit, guards, rentals, sessions
from app.config import PRODUCTION, load_settings
from app.domain import Account, Category, Role, Status, visible_to
from app.storage import (
    add_item,
    persist,
    clear_review,
    create_engine_for,
    create_schema,
    delete_item,
    edit_item,
    flag_review,
    load_items,
    load_quarantine,
    new_session,
    set_status,
)

#: The built Vue bundle. Absent until the frontend has been built, which is why
#: the mount is conditional rather than assumed.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

#: One body for every refused login, or the endpoint enumerates accounts for anyone
#: willing to ask twice.
INVALID_CREDENTIALS = "Invalid email or password"


class Credentials(BaseModel):
    email: str
    password: str


COMPANY_DOMAIN = "@booksy.com"  # ADR-0019


class NewAccount(BaseModel):
    email: str
    password: str
    role: Role

    @field_validator("email")
    @classmethod
    def on_the_company_domain(cls, email: str) -> str:
        """On the request model, so `bootstrap_admin`'s exemption is structural
        (ADR-0019). `endswith` on the whole suffix — `attacker@booksy.com.evil.net`
        and `someone@notbooksy.com` both pass the looser checks."""
        candidate = email.strip()
        if not candidate.lower().endswith(COMPANY_DOMAIN):
            raise ValueError(f"email must be on the {COMPANY_DOMAIN} domain")
        # `@booksy.com` itself ends with the domain and names no mailbox.
        if not candidate[: -len(COMPANY_DOMAIN)]:
            raise ValueError(f"email needs a name before {COMPANY_DOMAIN}")
        return candidate


class ReturnReport(BaseModel):
    """The optional half of a return (ADR-0020). Optional because nearly every
    return is fine; present-and-blank is refused because a flag reading `"   "`
    blocks the item and tells the resolving admin nothing."""

    issue: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None


class RoleChange(BaseModel):
    role: Role


class NewHardware(BaseModel):
    """Only `name` is required — real seed rows arrive with neither brand nor date,
    and refusing them here would make the API stricter than the data it stores."""

    #: Trimmed before length is checked: a name of spaces renders as a blank row,
    #: indistinguishable from a rendering bug.
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    brand: str | None = None
    purchase_date: date | None = None
    serial_number: str | None = None
    category: Category | None = None


class HardwareEdit(BaseModel):
    """`PATCH /api/hardware/{id}` — partial on purpose. `model_fields_set`
    distinguishes "brand: null" (clear it) from "brand absent" (leave it); treating
    absence as null is how fixing a name typo quietly blanks the brand."""

    status: Status | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    brand: str | None = None
    purchase_date: date | None = None
    serial_number: str | None = None
    category: Category | None = None
    #: Editable because `notes` is often the fault itself — a release certifying
    #: "fixed" against standing fault text is the false record ADR-0017 closes.
    notes: str | None = None


class ReviewOutcome(str, Enum):
    """Two members and no third: "dismissed" would clear the flag while asserting
    nothing about the device — the hole ADR-0017 exists to close."""

    RELEASED = "released"
    REPAIR = "repair"


class ReviewRelease(HardwareEdit):
    """`POST /api/hardware/{id}/clear-review` — an edit with a mandatory reason:
    releasing asserts the record is now correct, and the change making it correct
    belongs in the same request. The edit is optional; the note never is."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    #: Defaulted, not required — mandatory would break the Phase 3 UI on deploy.
    outcome: ReviewOutcome = ReviewOutcome.RELEASED


#: Typed in full — the route destroys rental history, and a bare POST is one
#: mistyped URL away from wiping what ADR-0011 protects.
RESET_CONFIRMATION = "reset the demo data"


class ResetConfirmation(BaseModel):
    confirm: Literal["reset the demo data"]


class Reason(BaseModel):
    """The mandatory reason on every admin override (ADR-0010)."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SearchQuery(BaseModel):
    """A question, not a filter — the filter object is the model's output, never the
    caller's input, or every employee gets the raw surface ADR-0015 closed."""

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class HeldBy(str, Enum):
    """Closed: an open `?held_by=<email>` would let any employee enumerate what a
    named colleague is holding."""

    ME = "me"


class SortKey(str, Enum):
    """Closed, so an unknown key is a 422 — silently unsorted rows for a typo is
    the bug a user reports as "sorting doesn't work sometimes"."""

    PURCHASE_DATE = "purchase_date"


#: Named once, because Phase 2 adds four routes under it.
HARDWARE = "/api/hardware"


def _claim(transition):
    """`_enforce` for a refusal that comes out of the atomic write (ADR-0008)."""
    try:
        return transition()
    except guards.GuardViolation as violation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(violation))


def _enforce(guard, *args, **kwargs) -> None:
    """Run a guard, translating its violation into `409` with the reason intact —
    once, here, so guards stay ignorant of HTTP."""
    try:
        guard(*args, **kwargs)
    except guards.GuardViolation as violation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(violation))


def create_app(env: Mapping[str, str] | None = None) -> FastAPI:
    """Build the application, or refuse to boot (ADR-0005)."""
    settings = load_settings(os.environ if env is None else env)

    # Under uvicorn the root logger has no handler, so application logs vanish even
    # though they are emitted — tests pass either way, only a real deploy notices.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s"
    )

    app = FastAPI(title="Hardware Hub")
    app.state.settings = settings

    engine = create_engine_for(settings.database_url)
    create_schema(engine)
    app.state.engine = engine
    #: The LLM seam (tests/llm_seam.py): a test's fake lands here, production leaves
    #: it None and `ai.resolve_client` builds the real client per request (ADR-0016).
    app.state.llm = None
    app.state.ai_cache = ai.ResponseCache()

    # DDL before the seed's session — SQLite cannot run CREATE TABLE on a second
    # connection while another holds a write transaction. Imported locally so `app`
    # does not depend on `scripts` just to be importable.
    rentals.create_schema(engine)
    audit.create_schema(engine)

    from scripts.seed import seed_if_empty

    seed_if_empty(engine)

    # Every boot, not only an empty one: a volume seeded before Phase 2 held an item
    # nobody could return, and `seed_if_empty` will never run again to fix it.
    with new_session(engine) as session:
        reconciled = rentals.reconcile_held_items(session, load_items(session))
        session.commit()
    if reconciled:
        logging.getLogger(__name__).info(
            "reconciled %d held item(s) that had no rental record", reconciled
        )

    # Admin #1 comes from the environment (ADR-0005) — the deploy target offers no
    # way to run a one-off command against the volume, so boot is the only place.
    accounts.create_schema(engine)
    with new_session(engine) as session:
        # Read before writing: `bootstrap_admin` is about to make the table
        # non-empty, and the demo account is created only on a never-used database —
        # so a deliberately deleted demo stays deleted.
        fresh = accounts.has_no_accounts(session)
        created = accounts.bootstrap_admin(
            session, settings.admin_email, settings.admin_password
        )
        demo = (
            accounts.bootstrap_demo(session, settings.demo_email, settings.demo_password)
            if fresh
            else None
        )
        backfilled = accounts.backfill_session_tokens(session)
        session.commit()

    log = logging.getLogger(__name__)
    if created is not None:
        log.info("bootstrapped admin #1 from the environment: %s", created.email)
    if demo is not None:
        log.info("created the published read-only demo account: %s", demo.email)
    if backfilled:
        log.info("issued session tokens to %d pre-existing account(s)", backfilled)

    # The enforcement point: per-route dependencies, not middleware — middleware
    # would take the unauthenticated login page down with everything else, and a
    # dependency puts the requirement in the signature a reader actually sees.

    def current_account(request: Request) -> Account:
        """The account behind this request, or `401`. The signature proves the
        subject was not tampered with; the per-request lookup proves it still refers
        to somebody — a token, never the recyclable row id (ADR-0013)."""
        token = sessions.subject_of(
            request.cookies.get(sessions.COOKIE_NAME), settings.secret_key
        )
        if token is not None:
            with new_session(engine) as session:
                account = accounts.find_by_token(session, token)
            if account is not None:
                return account
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue"
        )

    def current_admin(account: Account = Depends(current_account)) -> Account:
        """The admin behind this request, or `403` — layered on `current_account` so
        an anonymous caller still gets the `401` that means "sign in"."""
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
        """Exchange a credential for a session cookie, or refuse identically —
        never echoing the submitted address."""
        with new_session(engine) as session:
            account = accounts.verify_credentials(
                session, credentials.email, credentials.password
            )

        if account is None:
            # Raised, not returned: a 401 that arrives with a Set-Cookie is worse
            # than a 200.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS
            )

        with new_session(engine) as session:
            token = accounts.session_token_for(session, account.id)

        response.set_cookie(
            sessions.COOKIE_NAME,
            sessions.issue(token, settings.secret_key),
            **sessions.cookie_kwargs(production=settings.environment == PRODUCTION),
        )
        return {"email": account.email, "role": account.role.value}

    @app.get("/api/session")
    def read_session(account: Account = Depends(current_account)) -> dict[str, Any]:
        """Who the caller is — an `HttpOnly` cookie is unreadable from JavaScript,
        so after a reload this is the route the client asks."""
        return asdict(account)

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    @app.get("/api/users")
    def list_users(_: Account = Depends(current_admin)) -> list[dict[str, Any]]:
        """Every account, for the admin who manages them."""
        with new_session(engine) as session:
            return [asdict(account) for account in accounts.list_accounts(session)]

    @app.post("/api/users", status_code=status.HTTP_201_CREATED)
    def create_user(
        new_account: NewAccount, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Create an account. Admin-only — there is no self-registration."""
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
            target = accounts.find_by_id(session, account_id)
            if target is None:
                raise HTTPException(status_code=404, detail="No such account")
            _enforce(guards.ensure_an_admin_remains, session, account_id)
            # The write comes *before* the read, deliberately. Guard-then-delete
            # read "holds nothing" without a lock, and a rent committed in the gap
            # stranded an active rental on a deleted account (test_lifecycle_race).
            # Deleting first takes SQLite's write lock; the rentals read runs behind
            # it, and a guard refusal rolls the uncommitted delete back.
            accounts.delete_account(session, account_id)
            _enforce(
                guards.ensure_account_holds_nothing,
                rentals.item_ids_held_by(session, account_id),
                target,
            )
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
        """The inventory, behind a session (ADR-0006). Typed query parameters, so a
        filter for a status that does not exist is a 422 rather than the whole
        inventory read as "everything matches"."""
        with new_session(engine) as session:
            items = load_items(
                session,
                status=status,
                sort_by_purchase_date=sort is SortKey.PURCHASE_DATE,
            )
            if held_by is HeldBy.ME:
                # Scoped by *account*, not "is it In Use" — getting it wrong hands
                # one employee's rentals to another (ADR-0007).
                mine = rentals.item_ids_held_by(session, account.id)
                items = tuple(item for item in items if item.id in mine)
        return [visible_to(asdict(item), account) for item in items]

    @app.post("/api/hardware", status_code=status.HTTP_201_CREATED)
    def add_hardware(
        new_item: NewHardware, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Add an item to the inventory. Admin-only; status is not caller-supplied
        (see `storage.add_item`)."""
        with new_session(engine) as session:
            item = add_item(
                session,
                name=new_item.name,
                brand=new_item.brand,
                purchase_date=new_item.purchase_date,
                serial_number=new_item.serial_number,
                category=new_item.category.value if new_item.category else None,
            )
            session.commit()
        return asdict(item)

    @app.patch("/api/hardware/{item_id}")
    def change_hardware(
        item_id: int, change: HardwareEdit, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """The status toggle and the edit, one guarded route — a parallel edit route
        would be a way around the status guards. An empty edit is a 422 (a no-op
        UPDATE would report success for a request that expressed no intent), and
        nulling `name` is refused: it is the one field that identifies the device."""
        sent = change.model_fields_set
        if not sent:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An edit must name at least one field to change.",
            )
        if "name" in sent and change.name is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An item cannot lose its name — it is the one field that "
                "identifies the device.",
            )
        with new_session(engine) as session:
            item = _item_or_404(session, item_id)
            if change.status is Status.REPAIR:
                _enforce(
                    guards.ensure_no_active_rental,
                    rentals.active_rental(session, item_id),
                    item,
                    "sent to Repair",
                )
                _enforce(guards.ensure_repair_does_not_bury_a_review, item)
            if change.status is not None:
                set_status(session, item_id, change.status)
            fields = {
                key: value
                for key, value in (
                    ("name", change.name),
                    ("brand", change.brand),
                    ("purchase_date", change.purchase_date),
                    ("serial_number", change.serial_number),
                    ("category", change.category.value if change.category else None),
                    ("notes", change.notes),
                )
                if key in sent
            }
            if fields:
                edit_item(session, item_id, **fields)
            session.commit()
        return {"id": item_id, "edited": sorted(sent)}

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
        """Claim an item. The atomic `UPDATE` decides; the guards phrase the refusal
        (ADR-0008)."""
        with new_session(engine) as session:
            try:
                rental = rentals.rent(session, item_id, account)
            except guards.GuardViolation:
                # Only *now* read the row, to say why. Reading first opens a
                # transaction the UPDATE must upgrade — six concurrent claimants
                # upgrading one SQLite read lock deadlock rather than serialise.
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
        item_id: int,
        body: ReturnReport | None = None,
        account: Account = Depends(current_account),
    ) -> dict[str, Any]:
        """Close your own rental, optionally reporting a fault (ADR-0009, ADR-0020).

        The returner may raise the flag the auditor may not: direct observation
        against inference, not human against model. The note becomes `review_reason`
        verbatim — the only first-hand account anyone will get. The return itself is
        unconditional, and an already-flagged item still returns: refusing a
        physical handover would leave somebody holding a device the system still
        believes they have.
        """
        issue = body.issue.strip() if body and body.issue else None
        with new_session(engine) as session:
            _item_or_404(session, item_id)
            rental = _claim(lambda: rentals.return_(session, item_id, account))
            if issue:
                flag_review(session, item_id, issue)
                audit.record(
                    session,
                    actor=account,
                    action=audit.Action.REPORT_ON_RETURN,
                    reason=issue,
                    item_id=item_id,
                )
            session.commit()
        return {
            "item_id": item_id,
            "rental_id": rental.id,
            "close_kind": "return",
            "needs_review": bool(issue),
        }

    @app.post(f"{HARDWARE}/{{item_id}}/force-return")
    def force_return_hardware(
        item_id: int, body: Reason, admin: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Recall an item from whoever holds it. Admin-only, reason mandatory; the
        transition writes its own audit row (ADR-0010)."""
        with new_session(engine) as session:
            _item_or_404(session, item_id)
            rental = _claim(
                lambda: rentals.force_return(session, item_id, admin, body.reason)
            )
            session.commit()
        return {"item_id": item_id, "rental_id": rental.id, "close_kind": "force_return"}

    @app.post(f"{HARDWARE}/{{item_id}}/clear-review")
    def clear_review_flag(
        item_id: int, body: ReviewRelease, admin: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Conclude a review: release, or confirm the fault and set Repair (ADR-0017).

        A release's reason must begin with `fixed:` — it asserts what *changed*, not
        that somebody looked — and the release carries the edit it certifies, in one
        transaction and one audit row; without that, "fixed: corrected the date" was
        written while the date stayed 2027-10-10. The repair outcome is exempt from
        `fixed:` (its reason describes what is wrong), and `409` when nothing is
        flagged: idempotency would file a mandatory reason against a non-event.
        """
        release = body.reason
        if body.outcome is ReviewOutcome.RELEASED and (
            not release.lower().startswith("fixed:")
            or not release[len("fixed:"):].strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='A release note must state what changed, starting with '
                '"fixed:" — e.g. "fixed: battery replaced, safe to issue". '
                "If the fault is real, conclude the review with the Repair outcome "
                f'instead. Got {release!r}.',
            )
        edited = body.model_fields_set - {"reason", "outcome"}
        if "name" in edited and body.name is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An item cannot lose its name — it is the one field that "
                "identifies the device.",
            )

        with new_session(engine) as session:
            item = _item_or_404(session, item_id)
            if not item.needs_review:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{item.name} is not flagged for review, so there is "
                    "nothing to clear.",
                )

            # A refused edit raises before the commit, so the item stays flagged
            # rather than released against a rejected fix. The outcome decides the
            # status for `repair`; an explicit `status` still wins for a release.
            new_status = (
                Status.REPAIR if body.outcome is ReviewOutcome.REPAIR else body.status
            )
            if new_status is Status.REPAIR:
                _enforce(
                    guards.ensure_no_active_rental,
                    rentals.active_rental(session, item_id),
                    item,
                    "sent to Repair",
                )
            if new_status is not None:
                set_status(session, item_id, new_status)
            fields = {
                key: value
                for key, value in (
                    ("name", body.name),
                    ("brand", body.brand),
                    ("purchase_date", body.purchase_date),
                    ("serial_number", body.serial_number),
                    ("category", body.category.value if body.category else None),
                    ("notes", body.notes),
                )
                if key in edited
            }
            if fields:
                edit_item(session, item_id, **fields)

            clear_review(session, item_id)
            audit.record(
                session,
                actor=admin,
                action=(
                    audit.Action.REVIEW_TO_REPAIR
                    if body.outcome is ReviewOutcome.REPAIR
                    else audit.Action.CLEAR_REVIEW_FLAG
                ),
                reason=body.reason,
                item_id=item_id,
            )
            session.commit()
        return {"item_id": item_id, "needs_review": False}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """Alive, and nothing else (the deliberate second exception to ADR-0006).
        No database read — it must answer while the volume is broken, which is
        exactly when somebody is asking."""
        return {"status": "ok"}

    @app.post(f"{HARDWARE}/{{item_id}}/flag-review")
    def flag_review_item(
        item_id: int, body: Reason, admin: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Put an item behind the review guard — the verb that makes an auditor
        finding actionable: the model proposed, a human decides here (ADR-0017)."""
        with new_session(engine) as session:
            item = _item_or_404(session, item_id)
            if item.needs_review:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{item.name} is already flagged for review — clear the "
                    "existing flag first if the reason has changed.",
                )
            _enforce(guards.ensure_item_can_be_flagged, item)
            flag_review(session, item_id, body.reason)
            audit.record(
                session,
                actor=admin,
                action=audit.Action.FLAG_REVIEW,
                reason=body.reason,
                item_id=item_id,
            )
            session.commit()
        return {"item_id": item_id, "needs_review": True}

    @app.post("/api/search")
    def semantic_search(
        body: SearchQuery, account: Account = Depends(current_account)
    ) -> dict[str, Any]:
        """Natural language in, real rows out — through the filter schema (ADR-0004).
        `mode` is an honest claim about which path answered (ADR-0016)."""
        cache = app.state.ai_cache
        cache_key = ai.normalise_query(body.query)
        if cache_key in cache.search_filters:
            filters = cache.search_filters[cache_key]
        else:
            client = ai.resolve_client(app.state)
            filters = None
            if client is not None:
                try:
                    filters = ai.semantic_filter(client, body.query)
                except ai.ModelUnavailable:
                    filters = None  # transient — deliberately not cached
                else:
                    # Cached even when None: asking again about the same question
                    # buys the same schema refusal for quota.
                    cache.search_filters[cache_key] = filters

        with new_session(engine) as session:
            if filters is not None:
                mode, items = "semantic", ai.select_items(session, filters)
            else:
                mode, items = "keyword", ai.keyword_search(session, body.query)
        return {
            "mode": mode,
            "items": [visible_to(asdict(item), account) for item in items],
        }

    @app.get("/api/admin/audit")
    def run_inventory_audit(admin: Account = Depends(current_admin)) -> dict[str, Any]:
        """The Inventory Auditor: computed per run, persisted nowhere (ADR-0014).
        Admin-only — derived content inherits its source's restriction (ADR-0012).
        No fallback: unavailability is a `503` with a reason, never a quieter answer
        under the auditor's name (ADR-0016)."""
        client = ai.resolve_client(app.state, timeout=ai.AUDIT_TIMEOUT_SECONDS)
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The AI layer is not configured: set GEMINI_API_KEY to enable "
                "the Inventory Auditor. Nothing else about the Hub is affected.",
            )
        with new_session(engine) as session:
            items = load_items(session)
            quarantine = tuple(asdict(record) for record in load_quarantine(session))

        # The client check stays above: feature-off refuses even with warm entries.
        cache = app.state.ai_cache
        fingerprint = ai.catalogue_fingerprint(items, quarantine)
        cached = cache.audit_findings.get(fingerprint)
        if cached is not None:
            return {"findings": cached}

        try:
            results = ai.audit_catalogue(client, items, quarantine)
        except ai.ModelUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"The model could not be reached, so the audit did not run: "
                f"{error}. Try again once the provider is back.",
            )
        cache.audit_findings[fingerprint] = results
        return {"findings": results}

    @app.post("/api/admin/reset-demo")
    def reset_demo(
        _body: ResetConfirmation, _: Account = Depends(current_admin)
    ) -> dict[str, Any]:
        """Put the seed's defects back — demonstrating the live instance consumes it.

        An HTTP route because Railway exposes no exec or SSH. Clears the blocker
        rather than bypassing it: the rentals are deleted first, so the reseed
        passes ADR-0011's guard instead of being exempted from it.
        """
        from scripts.seed import SEED_PATH, ingest

        report = ingest(json.loads(SEED_PATH.read_text(encoding="utf-8")))
        with new_session(engine) as session:
            cleared_rentals = rentals.clear_all(session)
            cleared_events = audit.clear_all(session)
            persist(report, session)
            restored = rentals.reconcile_held_items(session, report.imported)
            session.commit()

        logging.getLogger(__name__).info(
            "demo reset: cleared %d rental(s) and %d audit event(s), reseeded %d items",
            cleared_rentals,
            cleared_events,
            len(report.imported),
        )
        return {
            "items": len(report.imported),
            "quarantined": len(report.quarantined),
            "rentals_cleared": cleared_rentals,
            "audit_events_cleared": cleared_events,
            "seed_rentals_restored": restored,
        }

    # Single origin (ADR-0001): the same app serves the API and the bundle, so
    # there is no CORS middleware to configure. Mounted last, at the root, so it
    # never shadows an API route.
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend"
        )

    return app
