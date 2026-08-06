# ADR-0003 — `needs_review` is a rentability guard, not a badge

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `brainstorm.md` v2 §1 (ADR-0003), §2, §3 Phase 2

## Context

The v1 plan preserved two seed records with semantic contradictions so the MVP 3
Inventory Auditor would have something to find: the Dell XPS 15, marked
`Available` with notes reading "battery swelling, do not issue without service",
and the MacBook Air M2, marked `Available` with a history of liquid damage.

At the same time the plan built a rental engine whose entire premise is that
guards make impossible states unreachable — and that engine would have issued
both machines to a user on request.

`needs_review` existed in v1 only as a flag surfaced in an admin queue. It changed
nothing about what the system would allow.

## Decision

A flagged item **cannot be rented**. Attempting to rent one returns `409` with a
readable reason, through the same guard machinery that rejects a rental against an
item in `Repair`.

## Consequences

- The safety hole closes without losing the demo. The contradictory records stay
  in the database, stay visible in the dashboard, and stay unrentable. The auditor
  still explains *why* in language a keyword scan could not produce.

- **Phase 0's quarantine work becomes load-bearing product rather than
  decoration.** The flag now has a behavioural consequence, which is the only thing
  that makes it worth setting.

- **Adds `test_cannot_rent_flagged_hardware` to the Phase 2 suite** (§3), asserting
  the Dell XPS specifically remains unrentable.

- **Broadens the Phase 3 test** from "never returns Repair items" to
  `test_semantic_search_never_returns_unrentable_items` — semantic search must
  respect the same guard, or the AI layer becomes a route around it.

- The guard lives in the state machine alongside the `Repair`, already-rented, and
  wrong-user guards. It is the same class of rule and must not be enforced in a
  route handler.

- **Unresolved consequence, and it is real:** nothing in the plan yet lets an admin
  *clear* `needs_review`. As written, a flagged item is unrentable permanently, and
  the two seed contradictions can never be returned to service even after inspection.
  Phase 1 surfaces the queue (§3) but does not resolve it. Either Phase 1 gains a
  clear-flag action, or the README states that flagged items require a database
  edit to release. This must not be left to be discovered at the Phase 2 gate.

- **Trade-off accepted:** ingestion can now make an item unrentable on structural
  grounds alone — record 6's future purchase date and record 10's missing fields
  are both quarantined and flagged (§2), so both are blocked from rental even
  though neither is unsafe to use. Availability is being traded for caution, and
  the direction of that trade is deliberate.
