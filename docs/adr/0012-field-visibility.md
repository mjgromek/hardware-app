# ADR-0012: Who sees what on a hardware item

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** Grilling 2, Q15, in `docs/PROMPT_TRAIL.md` Session 9

## Context

`GET /api/hardware` returns whole items to every signed-in account. ADR-0006 closed the
anonymous half of that; the field-level half is an open `/security-review` finding, carried
in the README's `⚠️ Partial` section: every employee sees `notes`, `history` and
`review_reason`, which are admin- and auditor-facing.

Phase 2 sharpens it. `assigned_to` stops being seed residue and becomes live data about
which colleague is holding which laptop.

## Decision

**Renter identity is visible to every signed-in user. `notes`, `history` and
`review_reason` are admin-only.**

## Consequences

- Hiding the renter would break the product. The point of `In Use` on an internal tool is
  knowing who to ask for the headphones; hiding it moves that conversation to Slack, where
  the tool cannot see it and the rental log stops matching reality.
- This **closes the open field-level `/security-review` finding** as a side effect of
  serialisation work Phase 2 has to do anyway, rather than as a separate hardening task
  that never gets scheduled.
- The line is drawn where the domain draws it: who holds equipment is operational,
  maintenance prose is auditor-facing. `notes` is where "battery swelling, do not issue
  without service" lives, and Phase 3's auditor writes findings into the same fields.
- **`GET /api/hardware`'s payload now depends on the caller's role**, which changes the
  contract table in `tests/conftest.py` and needs a test that a `user` does not receive
  the restricted fields, because a serialiser that forgets is invisible to every existing test.
- **Trade-off accepted:** a `user` can no longer see why an item is flagged, only that it
  is. The review queue becomes an admin screen in substance. That is consistent with
  ADR-0003: the flag's job for a non-admin is to explain why they cannot rent it, and
  the `409` reason already does that.
