# ADR-0010: One audit table for admin overrides
- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** Grilling 2, Q6 (as amended)/Q11/Q13, in `docs/PROMPT_TRAIL.md` Session 9
## Context
Phase 2 introduces two admin actions that override what an ordinary user may do:
force-returning somebody else's rental (ADR-0009) and clearing `needs_review` (ADR-0003
assigns the mechanism here). Both are assertions a later incident interrogates: the Dell
XPS is exactly the item where "cleared by admin, no reason given" would be indefensible.

## Decision

**One `audit_events` table**, not one per verb: `(id, actor_account_id, actor_email,
action, item_id, rental_id, reason, created_at)`. `action` is a **closed enum** and
`reason` is **mandatory free text**.

**Ordinary rent and return write nothing here.** A user renting a laptop is the product
working and the `rentals` row is its record; this table is for an admin doing what an
ordinary user could not.

**Clearing `needs_review`** is allowed regardless of status, returns `409` if the item is
not flagged, and gains no re-flag counterpart in Phase 2.

## Consequences

- `hardware_quarantine` is not reused: `persist` has replace semantics, so an audit trail
  there survives only until the next documented reseed.
- Two tables for one concept is the shallow-module smell `architecture-scout` would flag
  next phase; one table with a closed action enum is where Phase 3's auditor findings land
  if they ever need an actor.
- **No backfill of Phase 1's admin verbs.** Role changes and account deletions were never
  observed; retro-writing events for them would be fabricating an audit trail, which is
  worse than a disclosable gap. Wiring them going forward is in `BACKLOG.md`.
- Clearing is refused on an unflagged item because idempotency would hide a UI bug *and*
  write a mandatory reason against a non-event. Status and the flag stay orthogonal, which is the
  reasoning that gave `needs_review` its own dashboard column rather than a fourth chip.
- **Trade-off accepted:** a mandatory reason can be typed as "ok". The field cannot force
  thought, only a record that somebody was asked.
