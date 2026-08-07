# ADR-0005: Admin bootstrap and the zero-admin invariant

- **Status:** Accepted
- **Date:** 2026-08-06
- **Source:** `brainstorm.md` v2 §1 (ADR-0005), §3 Phase 0 and Phase 1

## Context

There is no self-registration: an admin creates every account. That constraint
was stated without a mechanism: nothing said how admin #1 comes to exist.

A second gap sat underneath it. If an admin can delete or demote themselves, the
system can reach zero admins, at which point no account can ever be created again
and the application is permanently locked. Two clicks reach that state. It is an
impossible state, in the app whose entire pitch is that impossible states are
unreachable.

## Decision

The seed creates admin #1 from `ADMIN_EMAIL` / `ADMIN_PASSWORD`. The app **refuses
to boot in production** if `ADMIN_PASSWORD` is unset, the same shape as the
existing secret-key check.

**`ENVIRONMENT` selects the regime**, and is the only variable read before the
guards run. `ENVIRONMENT=production` is strict: `SECRET_KEY` and `ADMIN_PASSWORD`
must both be present and non-empty, and an empty string is treated as absent, since
accepting it would bootstrap an admin nobody can log in as, which is the
zero-admin state by another route. Any other value, including an unset
`ENVIRONMENT`, is permissive: settings load with development defaults and the app
runs with no environment configured at all.

The asymmetry is deliberate. A guard that also blocks `git clone && pytest` gets
switched off by whoever hits it first, and a guard that is off is worth nothing.
The strictness belongs where the deployment is real.

"At least one admin exists" is enforced as a **guard in the same layer as the
rental guards**, returning `409`. It is the same class of invariant and must not
live somewhere else.

A **separate demo account** goes in the README, not the real admin credentials.

## Consequences

- **Adds `test_app_refuses_to_boot_without_admin_password`** to Phase 0 (§3), so the
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

- **Amended after `architecture-scout`, Phase 2: the guard is check-then-act, and a
  race defeats it.** `ensure_an_admin_remains` reads `count_admins()`, and the write
  that acts on the answer is a separate statement. Two concurrent demotions of the
  final two admins both read `2`, both pass, and both write. **Reproduced: two
  `PATCH /api/users/{id}` requests returned `200` and `200`, leaving zero live
  admins.** That is precisely the state this ADR exists to make unreachable.

  **Not fixed, deliberately.** The trigger is simultaneous demotions on an internal
  tool with two admin accounts, and the fix is already written down one ADR over:
  ADR-0008 settles that a read-then-decide guard cannot win a race and that the claim
  belongs in a conditional `UPDATE` whose rowcount is the decision. The same shape
  applies here, `UPDATE users SET role='user' WHERE id=:id AND (SELECT count(*) …) > 1`,
  and it is `guards.py` plus `accounts.py`, no wider. In `BACKLOG.md` and the README's
  `⚠️` section, with the condition that makes it worth doing.

  Worth saying plainly: this ADR claimed an invariant the code enforces only under
  sequential access. The claim was too strong from the day it was written, and the
  single-guard framing is what hid it: the rental engine had the same problem and
  solved it, three ADRs later, without anybody noticing the older guard shared it.

- **Trade-off accepted:** env-var bootstrap means rotating the admin credential is
  a redeploy, and the initial password exists in the platform's environment
  configuration rather than only as a hash. In production this would be a
  first-run forced password change; that is not built.
