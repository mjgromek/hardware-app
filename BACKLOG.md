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
