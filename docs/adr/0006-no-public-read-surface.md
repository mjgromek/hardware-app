# ADR-0006: No public read surface

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** Phase 1 red tests; `BACKLOG.md` (raised by `test-author`, resolved by
  the human); brief, "only admin-created users can access the Hub"

## Context

`GET /api/hardware` returned whole items to anyone with the URL, and whole items
include `notes` and `history`. The deployed v0 was therefore publishing, on the open
internet:

- the Dell XPS 15's note, "battery swelling, do not issue without service"
- the MacBook Air M2's history of liquid damage
- every other maintenance record, quarantine reason and review flag in the inventory

These are internal maintenance records about company equipment. Nothing about them
is intended for an anonymous reader, and no authentication stood between them and
one. ADR-0002 deliberately keeps that free text in the database as the Phase 3
auditor's raw material, which makes the exposure worse rather than incidental: the
fields exist precisely because they are candid.

The brief's rule, that only admin-created users may access the Hub, says the same thing
and is the supporting citation. It is not the argument. The argument is that the
endpoint was serving internal records to the public, and would have kept doing so.

This surfaced from the Phase 1 red tests. `test-author` wrote them reading
`/api/hardware` anonymously, because Phase 0's green tests did, and it filed the
question rather than deciding it, because turning a green test red is not a test author's
call. The honest reading is that the endpoint was wrong when it shipped in Phase 0,
not that Phase 1 changed the requirement.

## Decision

**No route serves data without a session.** `GET /api/hardware` requires an
authenticated caller and returns `401` without one. This holds for every data route
added later, including Phase 3's.

The static bundle and the login route stay reachable unauthenticated, because they
are what an unauthenticated caller needs in order to stop being one.

## Consequences

- **Phase 3's semantic-search endpoint is not public**, and that is now settled
  before it is written rather than argued about at the Phase 3 gate. It reads the
  same `notes` and `history`, and an LLM-shaped route around the guard is still a
  route around the guard, the same reasoning ADR-0003 applies to rentability.

- **`401` unauthenticated, distinct from `403` forbidden.** The dashboard's first
  paint is an unauthenticated fetch, and the Vue client uses the status to choose
  between the login screen and an error. Pinned by
  `test_inventory_requires_a_session`.

- **The tempting implementation is blocked by a test that already passes.** One
  middleware refusing everything would take the login page down with it;
  `test_serves_built_bundle_at_root` fetches `/` with no session and is green, so
  that shape turns a passing test red rather than shipping.

- **Three Phase 0 tests were amended.** `test_api_returns_hardware_items` logs in
  first and asserts exactly what it asserted before. The two boot-seed tests read
  through `app.storage` instead of over HTTP: their subject is what boot did to the
  table, not who may read it, and giving them a login would couple every future auth
  regression to a seeding failure. The reversal is recorded in `BACKLOG.md` as
  resolved rather than deleted.

- **This narrows the `notes`/`history` exposure. It does not close it.** Every
  signed-in employee still sees `notes`, `history` and `review_reason` on every item.
  Those are admin- and auditor-facing fields, and "not public" is a weaker property
  than "visible only to the roles that need them", and this ADR buys the first and not
  the second. Field-level authorization is **`/security-review`'s problem this
  phase**, before the Phase 1 gate, not deferred past it.

- **Trade-off accepted:** the inventory can no longer be demonstrated by opening a
  URL, so any reviewer or screenshot needs credentials. That cost is real for a
  submission meant to be looked at, and it is the correct direction of trade:
  publishing maintenance records to make a demo one click shorter is not a bargain.
