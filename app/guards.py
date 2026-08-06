"""Guards — preconditions that make an illegal transition impossible.

A guard is not a permission check. Authorization answers "may *you* do this"; a guard
answers "may this be done *at all*", and the two get different status codes: `403`
versus `409 Conflict` with a readable reason (CONTEXT.md).

**This module exists so the answer is not written twice.** ADR-0005 puts the
zero-admin invariant in the same layer as the rental guards, and ADR-0003 puts
`needs_review` there too. A guard implemented inside a route handler is a guard the
next route forgets — Phase 2 adds rent and return, which need the same treatment, and
they must find a layer here rather than a precedent of inline `if` statements.

Guards raise. They do not return booleans, because a caller can ignore a boolean and
a reviewer cannot see that it was ignored.
"""

from __future__ import annotations

from app import accounts
from app.domain import HardwareItem, Role, Status
from app.storage import Session

__all__ = [
    "GuardViolation",
    "ensure_an_admin_remains",
    "ensure_item_is_rentable",
    "ensure_no_active_rental",
]


class GuardViolation(RuntimeError):
    """An operation was well-formed and permitted, and would break an invariant.

    Carries the reason as its message because the reason is half the point: a `409`
    with no explanation leaves the UI nothing to show the person who tried, and they
    cannot tell a bug from a rule.
    """


def ensure_an_admin_remains(
    session: Session, account_id: int, *, becoming: Role | None = None
) -> None:
    """Refuse an operation that would leave the system with no admin (ADR-0005).

    Covers both routes to the same lockout, because either one alone leaves it
    reachable: **deleting** the last admin, and **demoting** them. Two clicks, and no
    account can ever be created again — there is no self-registration, so nobody can
    let themselves back in.

    ``becoming`` is the role the account is on its way to, or ``None`` for a deletion.
    A demotion to ``admin`` is not a demotion and is not refused; the guard fires only
    when the count would actually reach zero, so promoting, renaming or deleting any
    non-last account is untouched.
    """
    account = accounts.find_by_id(session, account_id)
    if account is None or account.role is not Role.ADMIN:
        return
    if becoming is Role.ADMIN:
        return
    if accounts.count_admins(session) > 1:
        return

    action = "demoted" if becoming is not None else "removed"
    raise GuardViolation(
        f"{account.email} is the last admin and cannot be {action}: with no admins "
        "left, no account could ever be created again. Promote another account first."
    )


def ensure_item_is_rentable(item: HardwareItem) -> None:
    """Refuse a rental the domain forbids, with one reason per cause (ADR-0008).

    A pure read, and deliberately *not* the decision — the atomic claim in
    `app.rentals.rent` is. This exists for the message: "this item is in Repair" is
    worth more to whoever asked than a bare refusal, and the three causes are
    genuinely different facts about the world.

    `needs_review` sits alongside `Repair` here because ADR-0003 makes the flag a
    rentability guard rather than a badge — the Dell XPS keeps its swelling battery
    whether or not anybody has written the note down as a status.
    """
    if item.status is Status.REPAIR:
        raise GuardViolation(
            f"{item.name} is in Repair and cannot be rented until it is released."
        )
    if item.needs_review:
        raise GuardViolation(
            f"{item.name} needs review before it can be rented: "
            f"{item.review_reason or 'the record could not be verified at import'}. "
            "An admin has to clear the flag first."
        )
    if item.status is Status.IN_USE:
        raise GuardViolation(
            f"{item.name} is already in use — somebody else has it."
        )


def ensure_no_active_rental(rental, item: HardwareItem, action: str) -> None:
    """Refuse an admin action that would strand somebody's active rental.

    Two callers, one rule (ADR-0009, ADR-0011): moving a held item to `Repair`, and
    deleting one. `CONTEXT.md` names "a rented item in Repair" as an impossible state,
    and a deleted item with a live rental leaves the rental pointing at nothing.

    Both are refusals rather than silent force-returns. An admin who needs the item
    back takes one deliberate extra action, and that action is the record.
    """
    if rental is None:
        return
    raise GuardViolation(
        f"{item.name} is out with {rental.renter_email} and cannot be {action} while "
        "it is held. Recall it first."
    )
