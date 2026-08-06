# CONTEXT — Shared Language

The vocabulary this project uses. Say "quarantine record", not "the row we couldn't
import properly". Consistent names make the codebase navigable and keep the agent
concise — one word instead of twenty.

Add terms here the moment a concept needs a name more than once.

---

## Core domain

**Hardware item** — a single piece of company equipment. Has `name`, `brand`,
`purchaseDate`, `status`. Never "device", "asset", or "gear" in code; those are
fine in prose.

**Status** — exactly one of `Available`, `In Use`, `Repair`. There is no fourth
value. The seed's `"Unknown"` is not a status (see *needs_review*).

**Rental** — one rent→return cycle. Has a renter, a start, and possibly an end.
An *active rental* has no end yet.

**Rent** — the transition `Available → In Use`, recording who took the item.

**Return** — the transition `In Use → Available`, closing the active rental.

**Guard** — a precondition that makes an illegal transition impossible. "Cannot rent
hardware in Repair" is a guard. Guards return `409 Conflict` with a readable reason.

**Impossible state** — any state the domain forbids: an item `In Use` with no
renter, two active rentals on one item, a rented item in `Repair`. The state
machine exists so these are unreachable, not merely unlikely.

---

## The seed data

**Seed** — the 11 records supplied in the brief. Deliberately dirty; the mess is
the exercise, not an accident.

**Quarantine record** — a seed row that failed validation and was written to
`hardware_quarantine` with a `reason` instead of being dropped. Ingestion is
lossy-free by design: nothing disappears silently.

**needs_review** — a flag on an imported item that arrived incomplete or
contradictory but is still usable. Where the seed's `"Unknown"` status ended up.
Surfaced to the admin as a queue.

**Semantic contradiction** — a record whose `status` conflicts with its own
`notes` or `history`. The Dell XPS is `Available` while its notes read "battery
swelling, do not issue without service"; the MacBook Air is `Available` with a
history of liquid damage. **These are left in the database on purpose** — they are
what the Inventory Auditor is built to find.

**Orphan rental** — an item marked `In Use` with no `assignedTo`. Seed id 2.
Resolved at import time.

**Source id** — the original `id` from the seed, preserved when a record had to be
re-keyed. The seed contains `id: 4` twice.

---

## The AI layer

**Semantic search** — natural-language query → filtered inventory. "Something to
test a mobile app on" returns phones and tablets.

**Filter object** — the structured, schema-validated object the LLM emits from a
natural-language query. The query hits SQLite through this object, never through
free-text SQL. Chosen over embeddings because with ~12 records, embeddings are
theatre.

**Inventory Auditor** — the AI pass that reads the whole catalogue including
`notes`, `history` and quarantine, and flags items a human should look at.

**Fallback** — plain keyword search, used whenever the LLM times out or errors.
The feature degrades; it never breaks.

---

## Process

**MVP / version** — one phase of `brainstorm.md`, one branch, one live deployment,
one tag. `v0` through `v5`.

**Review gate** — the human checkpoint between versions. Automated checks only
*open* the gate; the human decides. The next branch does not exist until it closes.

**Deepening** — refactoring toward deep modules: more behaviour behind a smaller
interface. What `architecture-scout` looks for.

**Shallow module** — one whose interface costs about as much to understand as its
implementation. It pays for nothing.

**Slice** — one vertical unit of work, end to end. "Admin can toggle Repair" is a
slice. "The admin panel" is not.

**Red / Green** — a failing test / a passing suite. Red always comes first, and it
must fail for the right reason: an import error is not red, it is broken.
