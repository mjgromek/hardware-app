# ADR-0011 — Rental data survives the reseed and the delete

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** Grilling 2, Q12 — `docs/PROMPT_TRAIL.md` Session 9

## Context

Two shipped paths destroy rental data silently the moment rentals exist:

1. **`persist` truncates `hardware`** and is a *documented live operation* — the README
   publishes `railway run --service hardware-hub python -m scripts.seed`. `seed_if_empty`
   guards the *boot* path on emptiness; nothing guards the manual one — so "a restart
   destroys every rental" was reachable by the documented command instead.
2. **`delete_item` deletes an item that is `In Use`**, leaving a rental pointing at
   nothing.

And `PRAGMA foreign_keys` is `0`, so any FK declared on `rentals` is documentation.

## Decision

Three protections, layered:

1. **`persist` refuses outright if any rental row exists**, rather than truncating.
2. **A guard refuses `delete_item` while an item has an *active* rental** — `409` with the
   holder named. A returned item stays deletable, with its history intact.
3. **`PRAGMA foreign_keys=ON`**, with `rentals.item_id` and `audit_events.item_id`
   declared, as the belt behind both.

## Consequences

- Enabling `foreign_keys` is unrelated to the locking pragmas `BACKLOG.md` warns against
  and does not affect the isolation `test_persist_does_not_commit` pins.
- Deleting a *returned* item stays legal, so `item_id` cannot be a blunt `RESTRICT` — the
  guard checks active rentals only. The README's reseed instructions need a line saying
  the command refuses once rentals exist.
- **Trade-off accepted:** a genuinely intended reseed of a live instance now requires
  clearing rentals by hand. That is the correct friction for an operation whose failure
  mode is silent data loss.
