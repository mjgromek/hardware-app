# Backlog

Non-blocking findings, written down instead of interrupting. Each entry says what was
found, why it matters, and when it becomes urgent. Nothing here is wrong today.

Entries are deleted when they are done, not annotated. The record of *why* something
changed lives in `AI_LOG.md` and `docs/adr/`; this file is only what is still owed.

---

## Before the Phase 1 gate

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

## Owned by Phase 2

**Clearing `needs_review` — assigned, not outstanding.** Nothing clears the flag, so a
flagged item is unrentable indefinitely (two of eleven in the seed). This sat here as
"urgent before the Phase 1 gate" and was resolved *by assignment* at that gate instead:
ADR-0003 now names Phase 2 as the owner, because clearing a rentability guard is a
transition in the rental state machine rather than an admin-panel field edit. Phase 2
delivers an admin-only action with an audit trail, gated on `app/guards.py`, pinned by
`test_admin_can_clear_needs_review` and `test_cleared_item_becomes_rentable`.

The Phase 1 queue also has no test at either layer — writing one would have meant
inventing the clear-flag semantics, which is the product decision above. It arrives with
the mechanism. *No longer overdue; it has an owner and two named tests.*

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

**vitest is not set up, and the condition it was waiting for has arrived.** `brainstorm.md`
§3 lists "pytest + vitest" as Phase 0 scope. This entry used to say "urgent when the
frontend grows logic worth testing" — it has: `HardwareTable`'s roving tabindex, the api
client turning a `401` into the login screen while a refused login stays on it, and the
filter counts computed from a second fetch. Three pieces of real logic, none asserted.
*Urgent when: now. It is the largest untested surface in the project.*

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

---

## Phase 1 UI — found while building it

**`POST /api/hardware` does not apply the checks ingestion applies.** Ingestion flags a
future purchase date (`needs_review`, seed id 6), but an admin adding an item by hand
can enter one and it lands unflagged. Two paths into the same table with two different
standards for what is suspicious — and the admin path is the one a human uses. The
route deliberately does not accept `status` or `needs_review`, so the fix is a shared
validator rather than a wider request body. *Urgent when: the auditor runs in Phase 3
and disagrees with what the admin panel allowed.*

**No `Serial Number` or `Category` field exists**, and the wireframes have both — a
column in the admin table and a select in the add-device form. Adding them means a
schema change, a migration on the mounted volume, and eleven rows where both are empty.
See `docs/WIREFRAME_JUSTIFICATION.md`. *Urgent when: the domain actually gains them —
serial numbers matter the first time two identical laptops need telling apart.*

**Nothing can edit an item's name, brand or date.** Only status and deletion. The
wireframe has an edit action; the app does not, because there is no endpoint. So a typo
like the seed's `Appel` can only be fixed in the database — and ADR-0002 deliberately
left that typo for the auditor to *find*, with no way to then act on the finding.
*Urgent when: Phase 3's auditor produces a correction somebody wants to apply.*

**A filtered dashboard fetches the inventory twice.** The filter chips show counts for
every status, so with a filter active the app fetches the filtered list and the whole
list — otherwise the counts would describe only what is already on screen. Eleven rows
makes this free. *Urgent when: the inventory outgrows one page and needs real
pagination, at which point counts belong in the API response.*

**Toasts overlap the bottom of the admin panel.** They are fixed bottom-right, and the
create-account row sits under them until they dismiss. *Urgent when: a toast covers a
control somebody needs while it is showing — reserve the space or move the stack.*
