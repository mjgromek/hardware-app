# ADR-0016: Search degrades announced; the auditor refuses; the key is a feature

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Grilling 3, Q3, in `docs/PROMPT_TRAIL.md` Session 14

## Context

CONTEXT.md fixes the fallback with keyword search on LLM timeout or error, so that "the feature
degrades; it never breaks." Three shapes were open: is degradation visible, does the
auditor degrade the same way, and what a missing `GEMINI_API_KEY` does to boot.

## Decision

1. **Degradation is announced.** The search response carries
   `mode: "semantic" | "keyword"` and the UI labels it.
2. **The auditor never falls back; it refuses loudly** with a `503` and a readable
   reason.
3. **A missing or invalid `GEMINI_API_KEY` is feature-off, not boot refusal.**
   Search runs keyword-labelled; the auditor returns its refusal; everything else is
   untouched.

## Consequences

- A silent fallback means a reviewer cannot tell whether the AI ever ran, and this
  project's pitch is that honesty is a feature. The mode field is the README's
  "graceful fallback" claim made checkable.
- A keyword auditor cannot find id 10, the one finding that proves the layer is not
  a regex (ADR-0002). A degraded audit silently reporting fewer findings while
  wearing the AI's name is worse than a refusal. Degrade the search, refuse the
  audit.
- `SECRET_KEY` and `ADMIN_PASSWORD` refuse boot because they guard security
  invariants (ADR-0005). This key guards a feature: rentals must not go down
  because a demo key rotated.
- `test_semantic_search_falls_back_on_api_error` asserts the mode field, not just
  the rows, because a fallback that lies about being the primary is the bug.
