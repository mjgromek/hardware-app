# ADR-0002 — Ingestion validates structure only

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `brainstorm.md` §7.1, §7.2; whole-project grilling, Q3

## Context

§7.1 catalogues ten defect classes across the 11 seed records. Eight are
structural — a duplicate primary key (`id: 4` twice), a status outside the enum
(`"Unknown"`), a purchase date in the future (`2027-10-10`), a `DD-MM-YYYY` date
among ISO ones, an empty brand, a null date, an orphan rental, a non-uniform
schema.

Two are not. Record 5 (Dell XPS 15) is marked `Available` while its notes read
"Battery swelling, do not issue without service." Record 11 (MacBook Air M2) is
marked `Available` with a history of liquid damage. §7.2 chose to leave both in
the database deliberately, as material for the MVP 3 Inventory Auditor to find.

The grilling identified a fork that had not been faced. "Battery swelling" and
"liquid damage" are keyword-findable. If ingestion *could* have detected them and
was written not to, then the problem the AI layer solves was manufactured for it
to solve — the most damaging available reading of an AI-centred submission.

## Decision

Ingestion validates **structure only**: schema shape, enum membership, primary-key
uniqueness, date format, and date plausibility. Semantic judgment over free-text
`notes` and `history` is explicitly outside its remit.

The boundary is deterministic-versus-judgment, and it is declared here rather than
discovered later.

**Parsing a field is structural; correcting a value is judgment.** Reading
`"22-05-2023"` as a date is deterministic — the field has a defined type and two
candidate formats, and normalising it loses nothing. Reading `brand: "Appel"` as
`"Apple"` is a guess about intent, correct only because a human recognises the
brand. Ingestion therefore normalises date formats and leaves `"Appel"` exactly as
the seed wrote it. The typo is the auditor's to surface.

**An off-enum status maps to `Available` + `needs_review`, not `Repair`.** The
seed's `"Unknown"` tells us the record is unidentifiable, not that the item is
broken; `Repair` would assert a physical fact ingestion has no evidence for.
Rentability does not depend on the choice — the ADR-0003 guard blocks a flagged
item under either status — so the status should carry the weakest claim the
evidence supports.

## Consequences

- The two contradictory records enter the `hardware` table, exactly as §7.2
  intended. The demo material for MVP 3 survives.

- **Safety is not addressed by this ADR.** These records remain `Available` and
  would be rentable on the strength of this decision alone. That hole is closed by
  ADR-0003, and the two ADRs must be read together.

- **The auditor now has to earn its place.** If it only ever flags the two records
  a keyword scan would catch, this boundary was a rationalisation. It is therefore
  required to flag record 10 — empty brand, null purchase date, `"Unknown"` status,
  no notes at all — as unidentifiable and needing physical audit. That is a
  judgment with no keyword signature, and it is the test of whether the AI layer
  does anything a regex could not.

- **The README must state plainly that a keyword scan would have caught the two
  obvious contradictions.** Claiming the LLM as the only possible detector for
  those two would be false, and the honest version is the stronger one.

- **Trade-off accepted:** a structural validator will pass any record whose fields
  are individually well-formed but collectively nonsensical. Detection of that
  class is deferred entirely to a layer that can fail, time out, or be wrong.
