# ADR-0014 — The auditor proposes, never disposes

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Grilling 3, Q1/Q4 — `docs/PROMPT_TRAIL.md` Session 14

## Context

The Inventory Auditor must flag the Dell XPS, the MacBook Air, the 2027 date, id 10
and `"Appel"`. `needs_review` is a rentability guard (ADR-0003) — an auditor that
sets it is an LLM changing what may be rented.

## Decision

**The auditor's vocabulary is a closed enum of finding kinds** —
`status_contradiction`, `unidentifiable`, `probable_misspelling` — exactly the three
classes ADR-0002 deferred. Each finding carries the evidence quote and a free-text
explanation.

**It proposes, never disposes.** It cannot set `needs_review`, cannot write
`review_reason`, cannot correct data. Findings are a **computed payload from an
admin-only route** — persisted nowhere, recomputed per run.

## Consequences

- ADR-0004's logic extended one layer: model output is validated *data*;
  deterministic code and humans are the only actors.
- An open vocabulary would let the auditor assert the untestable ("this laptop seems
  old") — the prose ADR-0004 exists to avoid. The closed enum is what
  `test_auditor_flags_unidentifiable_item` can pin.
- Admin-only is not a choice: every finding quotes `notes`/`history`, and derived
  content inherits its source's restriction (ADR-0012 untouched).
- `review_reason` keeps **human authors only** — ingestion, and the admin flagging
  through ADR-0017's verb — never the model. Its one consumer stays `clear-review`,
  which deletes it. LLM prose in a field an admin's clear action erases would
  entangle two lifecycles — so the "does the auditor's write change the field's
  visibility" question dissolves rather than gets answered.
- Nothing persisted: no new table for the demo reset to erase, no staleness
  question. Findings gain an actor only when one becomes a flag — ADR-0017, a
  human's act, in the `audit_events` table ADR-0010 reserved for exactly that.
