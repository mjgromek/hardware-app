# ADR-0019: Every account is on the company domain

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Phase 4, the lockout check performed before implementing domain validation

## Context

Phase 4 calls for restricting accounts to `@booksy.com`. Before writing it, the existing
addresses were checked against the rule, and two of the four failed:

| | Address | Passes |
| --- | --- | --- |
| Local bootstrap admin (`DEVELOPMENT_DEFAULTS`) | `admin@localhost` | ❌ |
| Deployed bootstrap admin (`ADMIN_EMAIL` on Railway) | `admin@hardwarehub.internal` | ❌ |
| Published demo account | `demo@booksy.com` | ✅ |
| Seed id 7's holder | `j.doe@booksy.com` | ✅ |

Enforcing the rule **at login** would have locked the only admin out of the live instance,
with no way back: `reset-demo` and account management are both admin-only, so recovery
would have meant changing a Railway variable and redeploying.

## Decision

**Every account in the project sits on `@booksy.com`, including the bootstrap admin.**
`ADMIN_EMAIL`'s development default becomes `admin@booksy.com`, and the deployed variable
is set to the same.

Domain validation therefore applies **at account creation, uniformly, with no exemption**.
Two properties make that safe rather than merely lucky:

- The bootstrap admin is created by `bootstrap_admin` from the environment, **not** through
  `POST /api/users`, so it never traverses the validated path. The exemption is structural
  rather than a special case somebody has to remember.
- With the defaults now on-domain, there is no address anywhere in the project that the
  rule would reject, so the exemption is not load-bearing even where it exists.

**Not at login.** A login check validates an address that was already validated when the
account was made, and its only distinctive power is to lock out accounts that predate the
rule. That is the failure mode, not the feature.

## Consequences

- **`admin@hardwarehub.internal` remains the live instance's admin until it is migrated.**
  Changing `ADMIN_EMAIL` alone does nothing to an existing volume: `bootstrap_admin` runs
  only when no admin exists, so a redeploy will *not* create `admin@booksy.com` beside it.
  Migrating means creating the new admin through the API and soft-deleting the old one.
- Once soft-deleted, ADR-0013 **permanently reserves** `admin@hardwarehub.internal`: the
  row is retained, so the address can never be reissued and the audit trail keeps naming
  the actor it always named.
- A fresh local database now bootstraps `admin@booksy.com` / `admin`, so a clone plus
  `pytest` plus the README's run instructions produce an account the rule accepts.
- **The validation itself is not yet implemented.** This ADR records the decision and the
  ground it stands on; the rule, its tests, and the modal's `@booksy.com` prefill are still
  to be written.
- **Trade-off accepted:** a deployment for a different company cannot use this default and
  must set `ADMIN_EMAIL`. It is a demo instance for one named company, and the alternative
  of a domain in configuration, validated against itself, is a generality nothing here
  needs.
