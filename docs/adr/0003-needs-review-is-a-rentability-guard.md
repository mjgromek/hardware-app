# ADR-0003: `needs_review` is a rentability guard, not a badge

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `brainstorm.md` v2 §1 (ADR-0003), §2, §3 Phase 2

## Context

The v1 plan preserved two seed records with semantic contradictions so the MVP 3
Inventory Auditor would have something to find: the Dell XPS 15, marked
`Available` with notes reading "battery swelling, do not issue without service",
and the MacBook Air M2, marked `Available` with a history of liquid damage.

At the same time the plan built a rental engine whose entire premise is that
guards make impossible states unreachable, and that engine would have issued
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
  `test_semantic_search_never_returns_unrentable_items`: semantic search must
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

- **Resolved by assignment, at the Phase 1 gate: Phase 2 owns the clear-flag
  mechanism.** Phase 1 took the second option above: the queue is surfaced read-only
  and the README says a flagged item requires a database edit to release. That closes
  the honesty requirement and leaves the product one intact: **nothing clears
  `needs_review`, so a flagged item is unrentable indefinitely**, and today that is two
  of eleven items in the seed. Phase 2 owns resolving it, and owns it for a structural
  reason rather than a scheduling one: the flag is a *rentability* guard, so clearing
  it is a transition in the same state machine as rent and return, and it belongs with
  the phase that builds that machine rather than bolted onto an admin panel beside it.

  What Phase 2 must deliver:

  - **An admin action that clears the flag**, not an edit to an arbitrary field. Only
    an admin, and never a side effect of any other operation.
  - **An audit trail.** Clearing is the assertion "somebody inspected this equipment
    and it is fit to issue", which is exactly the claim a later incident asks about.
    A cleared flag that leaves no record of who cleared it and why turns the
    quarantine trail Phase 0 built into decoration at the one moment it matters,
    and ingestion already writes a reason for every divergence, so the release must
    too. See `docs/DATA_AUDIT.md` for what the flag currently records.
  - **Gated on the same guard layer** (`app/guards.py`), for the reason this ADR
    already gives about `needs_review` itself: the rule that decides whether a
    transition is legal must not be enforced in a route handler.

  Pinned by `test_admin_can_clear_needs_review` and
  `test_cleared_item_becomes_rentable` (§3 Phase 2). The second is the one that
  matters: clearing a flag that does not change rentability is the decoration this
  ADR exists to prevent, in a new place.

- **Amended by grilling 2 (2026-08-06): the guard layer is not the sole decision point
  for the rent transition.** This ADR says a guard "must not be enforced in a route
  handler", and that stands. But a guard reads state and then decides, and a read
  followed by a write cannot win a race: two users claiming one `Available` item would
  both pass the same pre-check. So the *claim* is an atomic `UPDATE … WHERE
  status='Available'` whose zero rowcount means the caller lost, and it lives in
  `app/rentals.py` alongside the transition it belongs to, not in `app/storage.py`
  (which makes no decisions) and not in `app/guards.py` (which cannot be atomic).
  Guards keep the pre-checks that produce readable reasons; the transition owns its own
  atomicity. See ADR-0008.

- **Trade-off accepted:** ingestion can now make an item unrentable on structural
  grounds alone: record 6's future purchase date and record 10's missing fields
  are both quarantined and flagged (§2), so both are blocked from rental even
  though neither is unsafe to use. Availability is being traded for caution, and
  the direction of that trade is deliberate.

- **Amended 2026-08-07 (Phase 4): review and Repair are mutually exclusive, in both
  directions.** The flag and the status are orthogonal, which is why the dashboard gives
  the flag its own column rather than a fourth chip, and the enum stays exactly
  `Available | In Use | Repair` (ADR-0002). Orthogonal is not the same as *unconstrained*,
  and one combination is incoherent rather than merely unusual.

  `Repair` says an admin has taken the item out of service and knows why. `needs_review`
  says nobody has decided yet. An item asserting both tells a reader neither, and it puts
  an entry in the review queue that cannot honestly be concluded: releasing it would
  return to service a device somebody deliberately withdrew, and the other outcome, sending
  it to Repair, is already where it is.

  Both halves now hold:

  - **Repair → not flagged.** Concluding a review in Repair clears the flag, because a
    review that reaches a conclusion is over (ADR-0017, second Phase 4 amendment).
  - **Flagged → not Repair.** `POST /flag-review` refuses an item already in Repair,
    `409` through the guard layer with a reason that says what to do instead. This was
    the open path: it accepted any unflagged item, whatever its status.

  **Deliberately narrow.** `In Use` and `needs_review` still coexist, and must: somebody
  holding a device can be told it is under review, and the flag is what stops the *next*
  rental rather than the current one. The exclusion is Repair-shaped, not a general rule
  against flagging busy items.

  **This is what lets display precedence be a presentation rule.** The status chip renders
  `In Repair > Rented > In Review > Available`, and its first comparison now decides
  nothing the data can actually produce. A precedence order that existed to break a tie
  between two states a row should never hold at once would be a patch over the hole; with
  the exclusion enforced at the write, the order is only about which of several *true*
  facts is the most useful to show.

  **Both write paths, not one.** The first version of this amendment guarded
  `flag-review` only, and the dashboard showed the forbidden pair within minutes: admin
  edit reaches `Repair` too, and `PATCH {"status": "Repair"}` on a flagged row wrote it
  with nothing in the way. That route now refuses as well, pointing the admin at the
  review conclusion, which sets the same status *and* records why, against their name.
  Silently clearing the flag there was the tempting alternative and would have concluded
  a review with no reason and no audit row, which is precisely what ADR-0010 and ADR-0017
  exist to prevent. "By construction" is a claim about every route that can reach the
  state, and it is only worth making after enumerating them.
