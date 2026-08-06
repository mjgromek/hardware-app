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
from app.domain import Role
from app.storage import Session

__all__ = ["GuardViolation", "ensure_an_admin_remains"]


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
