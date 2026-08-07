# ADR-0015: The filter schema has no restricted-field predicates

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Grilling 3, Q2, in `docs/PROMPT_TRAIL.md` Session 14

## Context

Semantic search results are serialised through `visible_to`, so a non-admin's payload
nulls `notes`/`history`/`review_reason` (ADR-0012). That is the easy half. If the
filter object can express a predicate **over** those fields ("items with battery
problems"), result-set *membership* becomes an oracle: a `user` learns the Dell XPS
has battery notes by seeing it match, fields nulled or not.

## Decision

**The filter schema has no `notes`/`history`/`review_reason` predicate, for anyone,
either role.** Queries express over public columns only: name, brand, status, dates,
the `needs_review` flag. **The keyword fallback obeys the same rule**, or the
degraded path leaks what the primary path cannot.

## Consequences

- The oracle is structurally unreachable rather than guarded against, the same
  shape as the partial unique index (ADR-0007): the schema makes the leak
  inexpressible instead of a serialiser having to remember.
- One schema for both roles. Role-branched validation would be a second place for
  ADR-0012's rule to drift from the first.
- This is ADR-0004's accepted trade-off, not a new one: expressiveness traded for a
  provable property. "Which items mention swelling" joins "which laptop for a long
  flight" in the set of queries that answer poorly, deliberately.
- Pinned from both sides: the same query on both paths, from a `user` session,
  against an item whose only match is in `notes`: the result set must not include
  it, semantic or keyword.
- Admins lose the expressiveness too. Acceptable: the auditor (ADR-0014) is the
  admin-facing reader of that prose, and it reads the columns directly rather than
  through search.
