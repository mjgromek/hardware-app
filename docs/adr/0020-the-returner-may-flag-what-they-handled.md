# ADR-0020 — The returner may flag what they handled

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Phase 4 — the last open loop in the equipment lifecycle

## Context

`needs_review` had exactly one way in: an admin acting on an Inventory Auditor finding
(ADR-0017). That covers faults visible in the *record* — a purchase date in the future, a
status outside the enum, a brand spelled `Appel`. It covers nothing about the physical
device.

Seed id 11's history already describes the gap. It reads *"Returned by user with a
note"* — the data has always implied a person handing something back and saying what was
wrong with it, and the system had no verb for it. The note survived as prose in a history
field that nothing acts on.

So the person best placed to notice a fault — the one who just had the device in their
hands — could report it only by finding an admin and telling them out of band. Meanwhile
the item went straight back to `Available`, rentable by the next person, carrying a fault
nobody had recorded.

## Decision

**A returner may set `needs_review` on the item they are returning, with their own note
as the reason.** `POST /api/hardware/{id}/return` takes an optional `issue`; when present
the return completes *and* the flag goes up, attributed to the returner.

### Why this does not contradict ADR-0014

ADR-0014 — *the auditor proposes, never disposes* — denies the model write access to this
exact field. Granting it to a plain `user` one phase later looks like the same power
handed to a lesser actor, and the distinction has to be stated or it reads as arbitrary
in hindsight.

**The line is direct observation against inference, not human against model.**

The auditor reasons over stored text. Everything it can conclude is a claim about the
*record*, and a claim about the record is exactly the kind of thing that should be
proposed to a human who can check it against the world. It has never touched the device.

A returner is reporting the world. "The screen flickers when the lid moves" is not an
inference over columns; it is testimony from the only person who has handled the
equipment recently, and it is unavailable from any other source. Requiring an admin to
re-derive it would mean requiring them to re-derive something they cannot observe — the
device is back on the shelf and the fault is intermittent.

The test of the line: **an admin acting on an auditor finding still goes through the
admin verb.** Authority did not move. What moved is that first-hand observation now has
somewhere to go.

### What it does not grant

- **No power to close somebody else's rental.** ADR-0009 is untouched: the `issue` field
  travels with a return you are entitled to make. Somebody who never held the device has
  no observation to report, and gets the same `409` they always did.
- **No power to clear a flag.** The loop stays asymmetric on purpose — a `user` can say
  "something is wrong", and only an admin can conclude that it is not, or that it is and
  the item goes to Repair (ADR-0017, second Phase 4 amendment).
- **No power to set status.** A returner reports; they do not adjudicate. `Repair` is the
  reviewing admin's conclusion.

## Consequences

- **The lifecycle loop closes.** Ingestion declines to judge (ADR-0002) → the auditor
  proposes (ADR-0014) → an admin flags (ADR-0017) *or a returner reports (here)* → an
  admin concludes in Release or Repair (ADR-0017, amended). Every state now has a way in
  and a way out, and each is attributable.
- **A reported item is immediately unrentable**, because `needs_review` blocks rental
  (ADR-0003). This is the substantive protection and needs no new mechanism: the fault
  cannot reach the next person while it is still only in one employee's memory.
- **`report_on_return` is its own audit action**, not `flag_review`. The actor class is
  the point — a reviewing admin's next move is to ask the person named on the row, and a
  trail that flattens both into one verb cannot tell them who to ask.
- **The reason is stored verbatim.** Same principle as ADR-0017's prefill: what gets
  recorded is the human's own words. Here it is stronger, because the note is the only
  first-hand account that will ever exist.
- **An already-flagged item still returns.** `flag-review` answers `409` in that
  situation, on the grounds that a mandatory reason filed against a non-event hides a UI
  bug. That reasoning does not survive contact with a physical handover: the return is a
  fact that has already happened, and refusing it would leave somebody holding a device
  the system still believes they have. The report is folded into the existing flag.
- **Trade-off accepted: a user can make an item unrentable.** In an internal tool for
  colleagues that is the intended power, and the blast radius is one item that an admin
  can release in one action with a recorded reason. The alternative — a report queue that
  does *not* block — optimises for the case where the reporter is wrong, at the cost of
  the case where they are right and somebody is issued a device with a swelling battery.
- **The empty report is refused.** A flag reading `"   "` blocks an item and tells the
  admin resolving it nothing, which is worse than no flag: same floor as every other
  mandatory reason in the project.
