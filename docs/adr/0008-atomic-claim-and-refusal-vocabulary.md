# ADR-0008: The atomic claim, and what a refusal says

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** Grilling 2, Q5/Q9/Q14, in `docs/PROMPT_TRAIL.md` Session 9

## Context

`brainstorm.md` §3 lists `test_concurrent_rent_only_one_succeeds` and names an "atomic
conditional UPDATE". That collides with ADR-0003's guard layer: a guard reads state and
then decides, and a read followed by a write cannot win a race. Two users claiming one
`Available` item both pass the same pre-check.

## Decision

**The transition owns its atomicity, and `app/rentals.py` owns the transition.** `rent` is
an `UPDATE hardware SET status='In Use' WHERE id=:id AND status='Available'` plus the
`rentals` insert, in one transaction; a rowcount of zero means the caller lost and gets a
`409`. Guards keep the pre-checks that produce readable reasons.

`rentals.py` owns the SQL rather than delegating to `app/storage.py`, whose docstring says
it "makes no decisions": a `WHERE status='Available'` clause is a decision.

**Refusal reasons are one per cause, not one per timing.** `Repair`, `In Use`,
`needs_review` each get their own readable `409`. The race loser receives the `In Use`
reason.

## Consequences

- **Amends ADR-0003:** the guard layer is not the sole decision point for this one
  transition. Said out loud rather than left as an inconsistency a reviewer finds.
  `guards.py` keeps the pure-read invariants and the pre-checks whose only job is a
  better message than a bare rowcount gives.
- A caller who loses a race is told "somebody else has it", which by the time it is told
  is simply the current state. A client rendering "another user claimed this microsecond
  before you" would leak implementation detail as UX.
- **Trade-off accepted:** the pre-check and the atomic write can disagree under load, so a
  guard can pass and the `UPDATE` still match zero rows. That is correct and is the point;
  the pre-check exists for the message, not for the decision.
