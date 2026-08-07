# CONTEXT: Shared Language

Say "quarantine record", not "the row we couldn't import properly". One word
instead of twenty. Add terms when a concept needs a name more than once.

## Domain

**Hardware item**: one piece of equipment. `name`, `brand`, `purchaseDate`,
`status`. Not "device", "asset" or "gear" in code.

**Status**: exactly `Available`, `In Use`, or `Repair`. No fourth value.

**Rental**: one rent→return cycle. An _active rental_ has no end yet.

**Rent**: `Available → In Use`, recording who took it.
**Return**: `In Use → Available`, closing the active rental.

**Guard**: a precondition making an illegal transition impossible. Returns `409`
with a readable reason.

**Impossible state**: anything the domain forbids: `In Use` with no renter, two
active rentals on one item, a rented item in `Repair`. The state machine makes
these unreachable, not merely unlikely.

## Seed data

**Seed**: the 11 records from the brief. Deliberately dirty; the mess is the
exercise.

**Quarantine record**: a row that failed structural validation, written to
`hardware_quarantine` with a `reason` instead of dropped. Nothing disappears.

**needs_review**: a flag on an imported item that arrived incomplete or
contradictory. Blocks rental (ADR-0003). Where the seed's `"Unknown"` ended up.

**Semantic contradiction**: `status` conflicts with the item's own `notes` or
`history`. Dell XPS: `Available`, notes say "battery swelling". MacBook Air:
`Available`, history says liquid damage. **Left in the database on purpose**,
they are what the Inventory Auditor exists to find.

**Orphan rental**: `In Use` with no `assignedTo`. Seed id 2. Released at import,
with a quarantine record recording the divergence.

**Source id**: the original seed `id`, kept when a record was re-keyed. The seed
contains `id: 4` twice.

## AI layer

**Semantic search**: natural-language query → filtered inventory.

**Filter object**: the schema-validated object the LLM emits. Queries hit SQLite
through it, never through free-text SQL. Chosen so the model cannot hallucinate
inventory and so the layer is unit-testable. (ADR-0004)

**Inventory Auditor**: the AI pass over the catalogue including `notes`,
`history` and quarantine, flagging items a human should look at.

**Fallback**: keyword search over `name` and `brand` only, used when the LLM times
out, errors, or says something the filter schema forbids. The feature degrades; it
never breaks, and the response says which path answered (ADR-0016).

**Finding**: one proposed judgment from the auditor: an item, a `kind` from the
closed enum (`status_contradiction` | `unidentifiable` | `probable_misspelling`),
the evidence quoted, an explanation. Proposed, never acted on, because acting is an
admin's flag (ADR-0014, ADR-0017).

## Process

**Phase**: one branch, one deployment, one tag. `v0`–`v3`.

**Review gate**: the human checkpoint. Automated checks only _open_ it.

**Deepening**: refactoring toward more behaviour behind a smaller interface.
What `architecture-scout` looks for. A **shallow module** is one whose interface
costs as much to understand as its implementation.

**Red**: a test failing on its own assertion. An import or fixture error is not
red, it is broken.
