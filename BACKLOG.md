# Backlog

Non-blocking findings, written down instead of interrupting. Each entry says what
was found, why it matters, and when it becomes urgent. Nothing here is wrong today.

---

## Storage surface (Phase 0)

**`create_engine_for` must not use `StaticPool`.** `test_persist_does_not_commit`
requires two `new_session(engine)` calls to get independent connections — a single
shared connection would let the onlooker session see uncommitted rows and fail the
test for a reason unrelated to `persist`. The constraint is correct (the other
storage tests' second-session reads are meaningless without it) but it is now
enforced by a test rather than stated anywhere in the module. *Urgent when: whoever
implements `create_engine_for` reaches for a pool class.*

**`PRAGMA locking_mode=EXCLUSIVE` would break the same test with an error rather
than an assertion.** The onlooker's SELECT runs while the writer holds a write
transaction; default journal mode and WAL both allow it. *Urgent when: someone
tunes SQLite pragmas for the Railway deployment.*

**No teardown counterpart to `create_engine_for`.** Nothing disposes the connection
pool. Fine under `tmp_path` in tests; the app will want one for clean shutdown.
*Urgent when: Phase 3 production hardening, or a shutdown hook appears.*

**`load_items` has no filter argument.** Fine at eleven rows. Phase 1's
`needs_review` queue and the dashboard's status filter will both want one, and
adding it later changes the signature six storage tests are written against.
*Urgent when: Phase 1 builds the dashboard.*

---

## Traceability

**`test_persist_does_not_commit`'s docstring names Phase 2's
`test_concurrent_rent_only_one_succeeds` directly.** Deliberate — it traces the
constraint to the thing depending on it — but it drifts if that test is renamed.
*Urgent when: Phase 2 writes its rental tests.*

---

## Documentation owed

**`docs/DATA_AUDIT.md` does not exist**, and is a Phase 0 deliverable per
`CLAUDE.md`. It must state three divergences (ids 2, 6, 10), and that **quarantined
no longer implies unrentable** — id 2's orphan rental is quarantined and rentable,
ids 6 and 10 are quarantined and blocked. `test_importer_reproduces_documented_audit`
already enforces the counts. *Urgent when: before the Phase 0 review gate.*

**`review_reason` duplication is unresolved.** Items carry the reason for their own
flag while the quarantine record carries the full narrative. Narrowed but not
removed — removing it would turn `test_seed_quarantines_unknown_status` red, and
that test is the human's to change. See `AI_LOG.md` [P0 · c6]. *Urgent when: Phase 1
builds the admin queue and has to decide where it reads the reason from.*

---

## Phase 0 scope not yet started

- Vue/Vite scaffold + vitest — `create_app`'s static mount is structurally present
  but unexercised, and `frontend/dist` does not exist
- CI
- Deploy v0 — §3 argues it "proves the pipeline before there is anything to lose",
  and there is now meaningfully more to lose than when the phase started

---

## Phase 0 final step (added while wiring the deploy)

**`test_serves_built_bundle_at_root` requires `npm run build` before `pytest`.**
It asserts against the real `frontend/dist`, which is gitignored. CI must build the
frontend before running the Python suite or that test fails for the wrong reason.
Deliberate — a test against a fixture directory would prove the mount works and not
that the *built bundle* is served. *Urgent when: CI is set up.*

**vitest is not set up.** `brainstorm.md` §3 lists "pytest + vitest" as Phase 0
scope. The frontend has no tests at all. *Urgent when: the frontend grows logic
worth testing — currently it is one fetch and a table.*

**`scripts.seed.main()` is untested.** It is wiring only: every step it calls has
its own coverage, and it has no branches. Worth a smoke test if it ever grows an
argument. *Urgent when: it takes a flag.*

**Admin bootstrap is not implemented.** ADR-0005 says the seed creates admin #1
from `ADMIN_EMAIL` / `ADMIN_PASSWORD`. There is no users table until Phase 1, so
`load_settings` currently validates those variables without anything consuming
them. *Urgent when: Phase 1 builds auth.*

**`/api/hardware` returns every field**, including `notes` and `history` — the free
text the Phase 3 auditor reads. **Narrowed, not closed:** the endpoint is no longer
public (see the Phase 1 entry resolving the session question), so the contradiction
material is no longer readable by a stranger with the deployed URL. What remains is
field-level: every signed-in employee sees `notes`, `history` and `review_reason`,
which are admin- and auditor-facing rather than employee-facing, and no test asserts
who may see them. *Urgent when: `/security-review` before the Phase 1 gate, or when
the auditor starts writing findings into these fields in Phase 3.*

**No health endpoint.** Phase 3 scope per `brainstorm.md`, but Railway healthchecks
would use one now. *Urgent when: the deploy needs a healthcheck path.*

---

## Seeding on boot is a deploy shim, not a migration strategy

**Production seeding belongs in a migration or a one-off job, not in application
startup.** Boot logic that writes data couples "the process started" to "the data
changed", which is the wrong coupling: it runs on every replica, on every restart,
and in every environment, and it puts a write path in the one code path that must
be able to run when the database is in an unknown state.

It is here because the deploy target gave no alternative. Railway's public API
exposes no exec or SSH, `preDeployCommand` silently did not execute across two
deploys, and `railway ssh` requires an SSH key the machine did not have — so there
was no way to run `python -m scripts.seed` once against the mounted volume.

The emptiness guard is what makes it safe rather than merely convenient: once the
rental engine exists the hardware table is never empty, so the seeding branch can
never run again and can never destroy a rental. That is a real invariant, pinned by
`test_boot_leaves_a_populated_database_untouched` — but it is protecting a design
that should not need protecting.

*Urgent when:* the app gets a second replica (two processes racing to seed the same
empty database), or a real migration story is needed — whichever comes first.

---

## Phase 1 — found while writing the red tests

**The Phase 1 HTTP contract is fixed by `tests/conftest.py`, not by a spec.**
Nothing in `brainstorm.md` or ADRs 0001–0005 names a route, a request body or a
success code for login, account management or the dashboard's query parameters. The
test module docstring now carries that table, so the tests are the spec. That is
acceptable under TDD but it is not where a contract belongs, and the implementer
cannot renegotiate it (they may not edit tests). *Urgent when: `PROJECT_SPEC.md` is
written, or the implementer's first commit disagrees with a path — the human, not the
implementer, resolves it.*

**Descending sort is unpinned.** `test_dashboard_sorts_by_purchase_date` asserts
ascending only, because the convention for direction (`?sort=-purchase_date` versus
`?sort=purchase_date&order=desc`) is undecided and guessing it would pin a coin
flip. A sortable dashboard column implies both directions. *Urgent when: the UI gets
clickable column headers.*

**Where a null purchase date sorts is unspecified.** Seed id 10 has no date. The
sort test asserts only that the item is not *dropped* and that the dated items are
ordered — first-or-last is deliberately left open. SQLite sorts NULLs first
ascending; a Python sort raises `TypeError` on `None`. Someone should decide, and the
answer should be visible in the UI, not incidental. *Urgent when: the dashboard shows
the sorted table to a human.*

**~~Whether `GET /api/hardware` requires a session is undecided.~~ RESOLVED — it
requires a session.** Filed as undecided because Phase 0 read the endpoint
anonymously in three green tests, and reversing that is a product call rather than a
test author's. **Decided by the human:** the brief admits only admin-created accounts
to the Hub, so an inventory endpoint readable by anyone with the URL contradicts the
brief. Any role qualifies — this is authentication, not an admin gate.

Consequences, all in `tests/`:

- `tests/test_auth.py::test_inventory_requires_a_session` pins the rule: anonymous
  `GET /api/hardware` → `401` exactly (not `403`; the Vue client uses the status to
  decide whether to show the login screen), and the refusal must not carry the
  catalogue in its body. It has a signed-in control, so "refuse everybody" cannot
  satisfy it.
- `test_app.py::test_api_returns_hardware_items` now logs in first. It asserts
  exactly what it asserted before.
- `test_app.py::test_boot_seeds_an_empty_database` and
  `test_boot_leaves_a_populated_database_untouched` now read the table through
  `app.storage` instead of over HTTP. Their subject is what boot did to the table;
  authenticating inside them would have coupled two seeding tests to the auth layer
  and made them unrunnable until login exists. Nothing is lost — that seeded rows
  also reach the wire is `test_api_returns_hardware_items`'s job.
- Both dashboard tests moved onto a signed-in `user` session, which means they now
  report as fixture-setup errors until `POST /api/login` exists. Accepted: the
  contract wins over the convenience of a prettier red.
- `GET /` stays public, or nobody can reach the login page. Already pinned by
  `test_serves_built_bundle_at_root`, which fetches it with no session — so an
  enforcement point that refuses everything turns a green test red.

*No longer urgent. Left here rather than deleted: the reversal is the record.*

**Password salting is pinned only obliquely.**
`test_password_is_hashed_not_stored_plaintext` asserts no stored value equals the
plaintext, its hex or base64 encoding, or an unsalted MD5/SHA-1/SHA-256 of it. That
catches the rainbow-table case, but the direct statement — *two accounts with the
same password store different digests* — needs to name the users table to find the
two credentials, and the table shape does not exist yet. *Urgent when: the users
table lands; add the per-user-salt test then.*

**Seven tests are blocked rather than red until `POST /api/login` exists** — the four
in `test_admin.py`, `test_password_is_hashed_not_stored_plaintext`, and both dashboard
tests once the session requirement moved them onto a logged-in client.
`admin_client` / `user_client` assert that login works before yielding, deliberately:
without that assertion a client that never authenticated would sail through
`test_non_admin_cannot_create_user` on a `403` that proves nothing. The consequence
is that those seven report as pytest *errors at setup* until login is implemented.
Of the remaining four, three fail on their own subject today
(`test_login_rejects_unknown_user`, `test_login_rejects_wrong_password`,
`test_inventory_requires_a_session`) and one —
`test_session_cookie_is_http_only_and_same_site` — fails in its own body on the same
missing route.
*Urgent when: sequencing the green commits — login must land first, and the suite
should be re-read at that point to confirm all eleven fail on their own assertions.*

**No test covers the `needs_review` queue, and `brainstorm.md` §3 does not list
one.** The queue is named Phase 1 scope; ADR-0003 also records, as an unresolved
consequence, that nothing lets an admin *clear* the flag — so a flagged item is
unrentable forever and the two seed contradictions can never return to service.
Writing a test would have required inventing both the queue's shape and the
clear-flag semantics, which is a product decision. *Urgent when: before the Phase 1
gate — ADR-0003 says explicitly this must not be discovered at the Phase 2 gate.*

**Logout, session expiry and login throttling are nowhere in scope.** The session
cookie has no tested lifetime, there is no route that ends a session, and the login
endpoint can be hit without limit on a deployment that publishes demo credentials.
None of the nine named tests touches any of it. *Urgent when: `/security-review`
runs before the Phase 1 gate.*

**Nothing proves that boot-seeded rows reach the wire.** Fallout from putting
`/api/hardware` behind a session. `test_boot_seeds_an_empty_database` and
`test_boot_leaves_a_populated_database_untouched` used to fetch the endpoint, so they
incidentally showed that what boot wrote was also servable; they now read through
`app.storage`, and `test_api_returns_hardware_items` seeds its own database rather
than booting into one. Each half is covered and the join is not — and the join is
precisely what runs on the deploy path, where boot seeding is the only mechanism
available (see the seed-on-boot entry above). The gap is one `load_items` call wide,
so the risk is low and the asymmetry is worth knowing about. *Urgent when: a
serialisation change lands, or the deployed instance is ever seen empty while the
table is not.*
