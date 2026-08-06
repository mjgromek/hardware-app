# ADR-0017 — The flag-review verb

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Grilling 3, Round 2 — `docs/PROMPT_TRAIL.md` Session 14

## Context

ADR-0010 shipped `clear-review` with no re-flag counterpart, deliberately. The
auditor (ADR-0014) proposes and cannot dispose — so without a re-flag verb, it finds
the Dell XPS and nothing can happen.

## Decision

**Phase 3 adds an admin `flag-review` action.** It sets `needs_review`, takes a
mandatory reason, and writes an `audit_events` row — the `action` enum grows
`flag_review`.

## Consequences

- "A flag that changes nothing is decoration" (ADR-0003), one level up: a finding
  nobody can act on is a report, not a product. This verb is what makes the
  auditor's output actionable.
- It completes the loop ADR-0002 opened: ingestion deliberately declined to judge,
  the auditor judges, **a human decides** — and the decision is recorded with an
  actor, which is exactly what ADR-0010 reserved `audit_events` for.
- The reason may be prefilled from a finding but is the admin's own, editable —
  the claim recorded is the human's, not the model's (ADR-0014).
- Refusal semantics, prefill mechanics and the UI surface are specification
  detail — settled in `docs/specs/phase-3.md`, per the Session 9 precedent of not
  spending grilling rounds on what does not change the decision's meaning.
- Symmetry with `clear-review` (ADR-0010): admin-only, mandatory reason, `409`
  refused on an item already in the state the verb produces.
