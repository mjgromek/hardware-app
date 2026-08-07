# ADR-0017: The flag-review verb

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Grilling 3, Round 2, in `docs/PROMPT_TRAIL.md` Session 14

## Context

ADR-0010 shipped `clear-review` with no re-flag counterpart, deliberately. The
auditor (ADR-0014) proposes and cannot dispose, so without a re-flag verb, it finds
the Dell XPS and nothing can happen.

## Decision

**Phase 3 adds an admin `flag-review` action.** It sets `needs_review`, takes a
mandatory reason, and writes an `audit_events` row; the `action` enum grows
`flag_review`.

## Amended in Phase 4: the reason describes a change the same action performed

Phase 4 required a release note beginning `fixed:`, and gave the admin no way to fix
anything from that action. Resolving seed id 6 meant writing *"fixed: corrected the
purchase date"* while the purchase date stayed `2027-10-10`. The note certified work the
system had not done, and `audit_events` recorded the certification as though it had,
which is worse than no note at all: a false record with an actor's name on it, in the one
table ADR-0010 exists so that an incident can interrogate.

So `POST /api/hardware/{id}/clear-review` carries the edit. `ReviewRelease` is
`HardwareEdit` with a mandatory `reason`: the fields are optional, the note never is, and
both land in **one transaction with one `audit_events` row**. Two rows would let the pair
come apart, and a reader finding the release would have to join it to an edit by timestamp to
learn whether the certified change happened.

A refused edit leaves the item flagged. Nothing is written before the commit, so an
off-enum `category` or a `Repair` toggle against a held item aborts the release rather
than publishing a note for a correction the server rejected.

The edit stays optional because not every finding is a field. Seed id 10's problem is that
nobody knows what the device *is*; an admin who has physically identified it has fixed
something the record cannot express as a column change.

## Consequences

- "A flag that changes nothing is decoration" (ADR-0003), one level up: a finding
  nobody can act on is a report, not a product. This verb is what makes the
  auditor's output actionable.
- It completes the loop ADR-0002 opened: ingestion deliberately declined to judge,
  the auditor judges, **a human decides**, and the decision is recorded with an
  actor, which is exactly what ADR-0010 reserved `audit_events` for.
- The reason may be prefilled from a finding but is the admin's own and editable, so
  the claim recorded is the human's, not the model's (ADR-0014).
- Refusal semantics, prefill mechanics and the UI surface are specification
  detail, settled in `docs/specs/phase-3.md`, per the Session 9 precedent of not
  spending grilling rounds on what does not change the decision's meaning.
- Symmetry with `clear-review` (ADR-0010): admin-only, mandatory reason, `409`
  refused on an item already in the state the verb produces.
- **Amended 2026-08-07 (Phase 4):** `clear-review`'s reason must begin with
  `fixed:`, as in "fixed: battery replaced, safe to issue", validated server-side,
  `422` otherwise, case-insensitive, and the prefix alone is refused as an empty
  reason wearing a costume. An admin must state what *changed*, not merely that
  they looked: ADR-0010 accepted "ok" as the floor for overrides generally; a
  release is the one override whose claim, fit to issue, an incident
  interrogates directly, so its floor is higher. The flag verb's reason is
  deliberately not prefixed: restricting an item asserts a problem, not a fix.
  The Review action also moves to the needs-review tab exclusively, giving one place to
  release an item, next to the reason it was held.
- **Amended again 2026-08-07 (Phase 4): a review concludes; it does not only
  absolve.** The first amendment demanded that a release state what changed, and
  left an admin who found a *real* fault with no honest move: leaving the flag set
  records no decision, and releasing certifies a repair nobody performed. That is
  the same false record one move earlier, and worse: a release makes the item
  rentable, so it ends with an unfit device in somebody's bag. `clear-review` now
  takes an `outcome`:
  - `released` (the default, so every existing caller is unchanged) keeps the
    `fixed:` note and leaves the item issuable.
  - `repair` takes a reason describing **what is wrong**, and is deliberately
    exempt from `fixed:`, because demanding it there would readmit the false record
    through the new door.

  Both clear `needs_review`, because both are conclusions, and both write exactly
  one `audit_events` row, because both are decisions with an actor. The repair
  outcome sets the status to `Repair` and adds no blocking mechanism of its own:
  unrentability comes from the guard that already refuses rentals on repair items,
  which is why the test asserts it through the renting seam rather than the column.
  The trail distinguishes them, `review_to_repair` rather than
  `clear_review_flag`, because a log that cannot tell "released as fit" from
  "confirmed unfit" cannot answer the first question an incident asks.

  A third outcome was considered and refused. `dismissed`, which would clear the flag
  and assert nothing, is the one somebody will ask for, and it is exactly the
  finding-shaped hole this ADR exists to close.
