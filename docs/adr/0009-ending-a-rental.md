# ADR-0009 — Who may end a rental, and Repair against a held item

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** Grilling 2, Q3/Q4 — `docs/PROMPT_TRAIL.md` Session 9

## Context

`CONTEXT.md` lists "a rented item in `Repair`" as an impossible state the machine must make
unreachable. Phase 1 already ships the route that reaches it: `PATCH /api/hardware/{id}`
calls `set_status` with no guard, so an admin can flip seed id 7 from `In Use` to `Repair`
today.

Separately, renter-only returns strand every item whose holder leaves the company — and
this system has no logout, let alone offboarding.

## Decision

**An admin cannot move a held item to `Repair`.** The transition is refused with `409` and
a reason naming the holder: recall it first. This retrofits a guard onto a shipped route.

**Two verbs end a rental, and they are not the same verb.** `return` is the renter's, and
the wrong-user guard on it is absolute. `force_return` is an admin's, requires a reason,
and writes an `audit_events` row (ADR-0010). The rental records which one closed it, in
`close_kind`.

## Consequences

- `test_cannot_return_someone_elses_rental` keeps the meaning its name promises. Folding
  admins into the ordinary verb would have made it pass for a `user` and mean nothing for
  an admin — and reviewers read test names.
- **Phase 1's `test_admin_can_toggle_repair_status` needs a companion**, not a change: it
  toggles an `Available` item and stays true. The new test is that the same toggle against
  a held item is refused.
- A swelling battery on a held laptop takes an admin two deliberate actions — force-return,
  then `Repair` — instead of one silent one. That buys an audit trail that is not fiction:
  no rental ends without a record of who ended it. Seed id 7 can only ever be ended this
  way, since nobody can authenticate as `j.doe@booksy.com` (ADR-0007).
