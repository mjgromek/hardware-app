# ADR-0013: Accounts are soft-deleted, and sessions name a token

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `/security-review` at the Phase 2 gate, two findings, both reproduced

## Context

`users.id` is declared `Integer, primary_key=True, autoincrement=True`, which SQLAlchemy
compiles for SQLite as a plain rowid alias, with **no `AUTOINCREMENT` keyword**. Deleting the
highest-id account frees its number, and the next account created is handed it.

Three things were keyed on that number, and all three broke:

1. **The session cookie.** Its subject was the row id. A deleted `user`'s untouched cookie
   was replayed after a replacement admin took the id, and `GET /api/session` returned the
   *new admin's* identity. Offboarding was silently undone and escalated.
2. **`rentals.account_id`.** A departed employee's active rental appeared in their
   successor's `?held_by=me`, and the successor could close it through the ordinary
   renter verb, the guard ADR-0009 calls "absolute".
3. **`audit_events.actor_account_id`.** A clear-flag decision made by one admin became
   attributable to whoever inherited their id.

The third is the one that decides this ADR. ADR-0010 exists so that "somebody inspected
this and it is fit to issue" can be interrogated later. That trail is only truthful while
**actor identity is stable**, and an id that can be reissued is not an identity.

## Decision

**Sessions name a per-account `session_token`**: 256 bits from `secrets`, issued once and
never reissued, signed into the cookie instead of the row id. A row id is a storage
detail, and using it as session identity made storage decisions into security decisions.

**Accounts are soft-deleted.** `deleted_at` is set, the row stays, and every read on the
authentication and listing paths filters `deleted_at IS NULL`. A soft-deleted account
never frees its id, cannot authenticate, and does not appear in `GET /api/users`.

**An account with an active rental cannot be deleted** (`409`, the guard layer). The token
fixes who a *cookie* names; it cannot fix `rentals.account_id`, which is still an integer.
This is what makes an inherited rental unreachable: no active rental outlives its owner.

## Consequences

- **Additive, so a live volume needs no destructive migration.** Both columns are added
  and backfilled on boot; the alternative, `sqlite_autoincrement=True`, only affects
  `CREATE TABLE` and so would not have fixed the deployed database at all.
- **Existing sessions invalidate** on the deploy that lands this. Accepted: there is no
  logout route, so an old-scheme cookie had no other way to end.
- **A deleted address cannot be reissued**, and recreating it answers `409`. Correct rather
  than incidental: the audit trail names actors by email as well as id, and reusing an
  address recreates the ambiguity this ADR removes, one field over.
- `count_admins` excludes soft-deleted rows, or the last-admin guard (ADR-0005) would be
  satisfied by ghosts and the system could reach zero live admins.
- **Trade-off accepted:** the users table grows forever and holds people who have left.
  On a fleet of this size that is nothing, and the alternative is an audit trail that
  quietly reassigns their decisions to somebody else.
