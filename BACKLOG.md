# Backlog

Non-blocking findings, written down instead of interrupting. Each entry says what was
found, why it matters, and when it becomes urgent. Nothing here is wrong today.

Entries are deleted when they are done, not annotated. The record of *why* something
changed lives in `AI_LOG.md` and `docs/adr/`; this file is only what is still owed.

---

## Before the Phase 1 gate

**No test covers the `needs_review` queue, and `brainstorm.md` §3 does not list one.**
The queue is named Phase 1 scope; ADR-0003 also records, as an unresolved consequence,
that nothing lets an admin *clear* the flag — so a flagged item is unrentable forever
and the two seed contradictions can never return to service. Writing a test would have
required inventing both the queue's shape and the clear-flag semantics, which is a
product decision. *Urgent when: now — ADR-0003 says explicitly this must not be
discovered at the Phase 2 gate.*

**Logout, session expiry and login throttling are in no phase's scope.** There is no
route that ends a session, the cookie has no lifetime, and the login endpoint can be
hit without limit on a deployment that publishes demo credentials. The session is also
**stateless by design** (`app/sessions.py`): an HMAC over the account id with no server
side, so there is nothing to invalidate — a leaked cookie stays valid until
`SECRET_KEY` changes, and logout can only clear the browser's copy. *Urgent when:
`/security-review` before the Phase 1 gate.*

**`/api/hardware` returns every field**, including `notes` and `history` — the free
text the Phase 3 auditor reads. **Narrowed, not closed:** ADR-0006 put the endpoint
behind a session, so a stranger with the URL no longer sees the contradiction material.
What remains is field-level: every signed-in employee sees `notes`, `history` and
`review_reason`, which are admin- and auditor-facing rather than employee-facing, and
no test asserts who may see them. *Urgent when: `/security-review` before the Phase 1
gate, or when the auditor writes findings into these fields in Phase 3.*

**No per-user-salt test, now that there is a users table to write one against.**
`test_password_is_hashed_not_stored_plaintext` asserts no stored value equals the
plaintext, its hex or base64 encoding, or an unsalted MD5/SHA-1/SHA-256 of it — which
catches the rainbow-table case. The direct statement, *two accounts with the same
password store different digests*, was unwritable while the table shape did not exist.
It exists now (`app/accounts.py` salts per call), and nothing asserts it. *Urgent when:
the next test commit — this is cheap and the claim is load-bearing.*

---

## Contract and UI decisions still open

**The Phase 1 HTTP contract is fixed by `tests/conftest.py`, not by a spec.** Nothing
in `brainstorm.md` or the ADRs names a route, a request body or a success code for
login, account management or the dashboard's query parameters; the fixture module's
docstring carries that table, so the tests are the spec. The implementation now matches
it, which means the contract is real — it is just not written anywhere a reader would
look first. *Urgent when: `PROJECT_SPEC.md` is written.*

**Descending sort is unpinned.** `test_dashboard_sorts_by_purchase_date` asserts
ascending only, because the convention for direction (`?sort=-purchase_date` versus
`?sort=purchase_date&order=desc`) was a coin flip. `SortKey` has one member today, and
a sortable dashboard column implies both directions. *Urgent when: the UI gets
clickable column headers.*

**Where a null purchase date sorts is decided by SQLite, not by anyone.** Seed id 10
has no date. `load_items` orders in SQL, which puts NULLs first ascending and never
raises; the test asserts only that the row is not dropped. So the answer is currently
incidental rather than chosen, and it will be visible in the dashboard. *Urgent when:
the sorted table is shown to a human.*

---

## Deploy and operations

**Seeding on boot is a deploy shim, not a migration strategy.** Boot logic that writes
data couples "the process started" to "the data changed": it runs on every replica, on
every restart, in every environment, and it puts a write path in the one code path that
must run when the database is in an unknown state.

It is here because the deploy target gave no alternative — Railway's API exposes no
exec or SSH, `preDeployCommand` silently did not execute across two deploys, and
`railway ssh` needs an SSH key the machine did not have. The emptiness guard is what
makes it safe rather than merely convenient: once rentals exist the table is never
empty, so the branch can never run again and can never destroy one. That invariant is
pinned by `test_boot_leaves_a_populated_database_untouched` — but it protects a design
that should not need protecting. Admin bootstrap now rides the same boot path, for the
same reason, though it is idempotent and additive rather than destructive.

*Urgent when:* a second replica exists (two processes racing to seed one empty
database), or a real migration story is needed — whichever comes first.

**Nothing proves that boot-seeded rows reach the wire.** Fallout from ADR-0006.
`test_boot_seeds_an_empty_database` and `test_boot_leaves_a_populated_database_untouched`
used to fetch `/api/hardware`, so they incidentally showed that what boot wrote was
servable; they now read through `app.storage`, and `test_api_returns_hardware_items`
seeds its own database rather than booting into one. Each half is covered and the join
is not — and the join is what runs on the deploy path. One `load_items` call wide, so
the risk is low and the asymmetry is worth knowing. *Urgent when: a serialisation change
lands, or the deployed instance is seen empty while the table is not.*

**No health endpoint.** Phase 3 scope per `brainstorm.md`, but Railway healthchecks
would use one now. *Urgent when: the deploy needs a healthcheck path.*

**No teardown counterpart to `create_engine_for`.** Nothing disposes the connection
pool. Fine under `tmp_path` in tests; the app will want one for clean shutdown.
*Urgent when: Phase 3 production hardening, or a shutdown hook appears.*

---

## Test-suite debts

**`test_serves_built_bundle_at_root` requires `npm run build` before `pytest`.** It
asserts against the real gitignored `frontend/dist`, deliberately — a fixture directory
would prove the mount works, not that the *built bundle* is served. CI must build the
frontend before the Python suite. *Urgent when: CI is set up.*

**vitest is not set up.** `brainstorm.md` §3 lists "pytest + vitest" as Phase 0 scope
and the frontend has no tests. *Urgent when: the frontend grows logic worth testing —
Phase 1's dashboard is the first candidate.*

**`scripts.seed.main()` is untested.** Wiring only: every step it calls has its own
coverage and it has no branches. *Urgent when: it takes a flag.*

**`test_persist_does_not_commit`'s docstring names Phase 2's
`test_concurrent_rent_only_one_succeeds` directly.** Deliberate — it traces the
constraint to the thing depending on it — but it drifts if that test is renamed.
*Urgent when: Phase 2 writes its rental tests.*

**`review_reason` duplication is unresolved.** Items carry the reason for their own flag
while the quarantine record carries the full narrative. Narrowed but not removed —
removing it would turn `test_seed_quarantines_unknown_status` red, and that test is the
human's to change. See `AI_LOG.md` [P0 · c6]. *Urgent when: the admin queue is built
and has to decide where it reads the reason from.*
