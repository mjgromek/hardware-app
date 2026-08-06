# ADR-0007 — The rental record

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** Grilling 2, Q1/Q2/Q7/Q10 — `docs/PROMPT_TRAIL.md` Session 9

## Context

Phase 2 needs to know who has what, and for how long. Three things already exist and
constrain the answer: `hardware.status` is what the seed ships and what 55 tests and the
dashboard filter assert against; `hardware.assigned_to` holds a bare email; and seed id 7
is `In Use` assigned to `j.doe@booksy.com`, an address with no account behind it.

## Decision

**`hardware.status` stays the source of truth; `rentals` is an append-only log beside it.**
One table, `ended_at` nullable, active means `NULL`. A **partial unique index on
`rentals(item_id) WHERE ended_at IS NULL`** makes "two active rentals on one item"
unreachable in the database rather than remembered by a guard.

The renter is stored **twice** — `account_id` for identity, `renter_email` as a snapshot,
so deleting an employee cannot erase the record that they held a laptop. The closer is
stored the same way, plus `close_kind` (`return` | `force_return`), because ADR-0009 makes
the closer possibly a different person from the renter.

**Seed id 7 becomes a rental row with `account_id = NULL`** and its email snapshot.
## Consequences

- Deriving `status` from `rentals` was rejected: it rewrites Phase 0 and Phase 1 for
  elegance, against a column the whole product already reads. Two tables (active/history)
  were rejected too — moving rows on return is two writes with a window where the rental
  is in neither or both.
- Seed id 7 is returnable only by force-return (ADR-0009) — nobody can authenticate as its
  holder. This is the honest representation of a rental that predates the account system,
  and it adds no divergence to `docs/DATA_AUDIT.md`: the row is imported as the seed
  states it.
- **Trade-off accepted:** `status` and `rentals` can now disagree if a write path forgets
  one of them. The single-statement transitions in ADR-0008 are what keep them together,
  and `test_rent_then_return_restores_available` is what notices if they drift.
