# ADR-0005 — Admin bootstrap and the zero-admin invariant

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `brainstorm.md` v2 §1 (ADR-0005), §3 Phase 0 and Phase 1

## Context

There is no self-registration — an admin creates every account. That constraint
was stated without a mechanism: nothing said how admin #1 comes to exist.

A second gap sat underneath it. If an admin can delete or demote themselves, the
system can reach zero admins, at which point no account can ever be created again
and the application is permanently locked. Two clicks reach that state. It is an
impossible state, in the app whose entire pitch is that impossible states are
unreachable.

## Decision

The seed creates admin #1 from `ADMIN_EMAIL` / `ADMIN_PASSWORD`. The app **refuses
to boot in production** if `ADMIN_PASSWORD` is unset — the same shape as the
existing secret-key check.

"At least one admin exists" is enforced as a **guard in the same layer as the
rental guards**, returning `409`. It is the same class of invariant and must not
live somewhere else.

A **separate demo account** goes in the README, not the real admin credentials.

## Consequences

- **Adds `test_app_refuses_to_boot_without_admin_password`** to Phase 0 (§3) — the
  bootstrap path is tested before any UI exists to exercise it.

- **Adds `test_cannot_remove_last_admin`** to Phase 1 (§3), covering both deletion
  and demotion. Either alone leaves the lockout reachable.

- The guard sits with the rental guards rather than in the user-management module,
  which means the guard layer is not purely about hardware state. That is
  deliberate: the organising principle is "invariants that must hold", not "things
  about hardware".

- **Published demo credentials on a public deployment**, listed in the README
  trade-offs table as a deliberate affordance. A reviewer logging in within ten
  seconds is worth more here than credential hygiene on a throwaway instance, and
  saying so openly is the point of the table.

- **Trade-off accepted:** env-var bootstrap means rotating the admin credential is
  a redeploy, and the initial password exists in the platform's environment
  configuration rather than only as a hash. In production this would be a
  first-run forced password change; that is not built.
