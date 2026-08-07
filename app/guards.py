"""Guards — preconditions that make an illegal transition impossible.

A guard answers "may this be done *at all*", not "may *you* do this" — `409` with a
readable reason, never `403` (CONTEXT.md). Guards raise rather than return booleans,
because a caller can ignore a boolean and a reviewer cannot see that it was ignored.
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
    "ensure_account_holds_nothing",
]


class GuardViolation(RuntimeError):
    """Carries the reason as its message — a bare 409 leaves the UI nothing to show."""


def ensure_an_admin_remains(
    session: Session, account_id: int, *, becoming: Role | None = None
) -> None:
    """Refuse deleting or demoting the last admin (ADR-0005).

    ``becoming`` is the role the account is on its way to, or ``None`` for a deletion.
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
    """One reason per cause (ADR-0008). A pure read — the atomic claim in
    `app.rentals.rent` is the decision; this exists only for the message."""
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


def ensure_item_can_be_flagged(item: HardwareItem) -> None:
    """Review and Repair are mutually exclusive by construction (ADR-0003, amended)."""
    if item.status is Status.REPAIR:
        raise GuardViolation(
            f"{item.name} is already in Repair, so it cannot also be flagged for "
            "review — an admin has taken it out of service and the reason belongs "
            "there. Release it from Repair first if the record itself is in doubt."
        )


def ensure_repair_does_not_bury_a_review(item: HardwareItem) -> None:
    """The mirror of `ensure_item_can_be_flagged` — admin edit was the route that
    could still produce the forbidden pair. Refused rather than silently clearing:
    clearing here would conclude a review with no reason and no audit row."""
    if item.needs_review:
        raise GuardViolation(
            f"{item.name} is under review, so it cannot be moved straight to Repair. "
            "Conclude the review with the Repair outcome instead — that records why, "
            "against your name, and sets the status in the same action."
        )


def ensure_no_active_rental(rental, item: HardwareItem, action: str) -> None:
    """Refuse an admin action that would strand an active rental (ADR-0009, ADR-0011)."""
    if rental is None:
        return
    raise GuardViolation(
        f"{item.name} is out with {rental.renter_email} and cannot be {action} while "
        "it is held. Recall it first."
    )


def ensure_account_holds_nothing(held_item_ids, account) -> None:
    """No active rental outlives its owner — `rentals.account_id` is a recyclable
    integer, and this guard is what makes an inherited rental unreachable (ADR-0013)."""
    if not held_item_ids:
        return
    raise GuardViolation(
        f"{account.email} still has {len(held_item_ids)} item(s) out "
        f"(ids {sorted(held_item_ids)}). Recall them first — an account cannot be "
        "removed while equipment is signed out to it."
    )
