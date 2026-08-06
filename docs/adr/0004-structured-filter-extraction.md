# ADR-0004 — Structured filter extraction over prompt-stuffing

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `brainstorm.md` v2 §1 (ADR-0004), §3 Phase 3

## Context

Semantic search turns a natural-language query into a filtered inventory view. At
roughly a dozen records, retrieval is not the problem — the entire catalogue fits
in a single prompt, so embeddings are dominated before the argument starts.

That makes the live question not embeddings-versus-filters but: why extract a
structured filter at all, rather than hand the model the whole catalogue and let
it answer?

The v1 justification was "with ~12 records, embeddings are theatre." That is a
scale argument, and scale arguments collapse the moment someone asks what happens
at 12,000 records — the answer would be "I would have chosen differently", which
means the decision was contingent rather than principled.

## Decision

The LLM emits a schema-validated filter object. SQLite returns the rows.

The justification is two properties that hold at any scale:

1. **The model cannot hallucinate inventory.** Every item a user sees provably
   exists in the database. Hand the model the catalogue and it can invent a
   fourteenth device, and nothing prevents it.
2. **The AI layer becomes unit-testable.** A deterministic object asserted against
   a mocked LLM. "Model reads catalogue, returns prose" is testable only by
   snapshot, which is barely.

Scale is a footnote, not the argument.

## Consequences

- `test_semantic_query_maps_to_filter_schema` runs deterministically against a
  mocked LLM in CI, with no live API dependency in the test suite (§3).

- Search must degrade rather than break: on API error or timeout the system falls
  back to keyword search (`test_semantic_search_falls_back_on_api_error`).

- Filter output is subject to the same guards as everything else —
  `test_semantic_search_never_returns_unrentable_items` (ADR-0003). The AI layer
  is not a route around the state machine.

- **The LLM provider becomes a late, cheap decision.** Gemini Flash, Claude Haiku
  and GPT-4o-mini are interchangeable here because the schema does the load-bearing
  work; the choice can wait until Phase 3 (§7).

- **This deletes "AI-native" as an architectural claim.** Two features hanging off
  a CRUD app is AI-*featured*, and asserting otherwise invites a reviewer to test
  the claim against the architecture. The README states the engineering positively
  instead — schema-validated output, guaranteed-real results, graceful fallback,
  deterministic tests — without editorialising about the brief's wording.

- **Trade-off accepted:** any query that cannot be expressed as a filter over the
  existing columns degrades to keyword search. A question like "which laptop should
  I take on a long flight" has no filter representation and will answer poorly.
  Expressiveness is being traded for provable correctness.
