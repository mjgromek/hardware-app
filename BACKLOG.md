# Backlog

Non-blocking findings, written down instead of interrupting. Each entry says what was
found, why it matters, and when it becomes urgent. Nothing here is wrong today.

Entries are deleted when they are done, not annotated. The record of *why* something
changed lives in `AI_LOG.md` and `docs/adr/`; this file is only what is still owed.

---

## Before the Phase 1 gate

**Logout, session expiry and login throttling are in no phase's scope.** There is no
route that ends a session, the cookie has no lifetime, and the login endpoint can be hit
without limit on a deployment that publishes demo credentials. The cookie is an HMAC over
a per-account token (ADR-0013) with no server-side session record, so a *leaked* cookie
stays valid until the account is deleted or `SECRET_KEY` changes.

**Narrowed by ADR-0013:** deleting an account now genuinely revokes its sessions —
`deleted_at` is set, the token is cleared, and the id is never reissued, so the cookie
matches nothing. Before that, `/security-review` showed a deleted account's cookie
reviving as whoever inherited its recycled id. What remains is the weaker original
property: no way to end *your own* session, and no expiry. *Urgent when: a per-session
revocation is needed — logging out one device rather than retiring the account.*

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

## Found while writing the Phase 2 tests

**ADR-0003 names the wrong item.** It says `test_cannot_rent_flagged_hardware` asserts
"the Dell XPS specifically remains unrentable", and the Dell XPS (seed id 5) is **not
flagged** — ADR-0002 makes ingestion structural only, so "battery swelling" is left for
the Phase 3 auditor and the item imports `Available` and unflagged. The rows ingestion
actually flags are id 6 (2027 purchase date) and id 10 (off-enum status). The test as
written derives the flagged set from the inventory instead of naming a row, so it covers
both and stays correct if Phase 3's auditor starts setting the flag. Nothing is broken;
the ADR's example sentence is just false and a reviewer reading it will look for a test
that cannot exist. *Urgent when: ADR-0003 is next edited, or the Phase 2 gate — a
one-line correction, not a decision.*

**Slice A and B ship no read surface for `rentals` or `audit_events`.** Three tests
(`test_rental_history_records_both_ends`, `test_seed_id_7_imports_as_an_accountless_rental`,
the two in `test_audit_events.py`) therefore read SQLite with raw SQL through
`app.state.engine`, which pins the column names from `docs/specs/phase-2.md` rather than
an API contract. Deliberate — importing `app.rentals` would have made every Phase 2 test
*broken* rather than *red* before the module existed — but it means a schema rename turns
four tests red for a reason that is not about behaviour. *Urgent when: Slice C's
`GET /api/hardware?held_by=me` lands, at which point the rental half can go through the
boundary and only the audit reads need the helper.*

**`audit_events` has no read surface at all, in any slice.** ADR-0010 builds the table
because "cleared by admin, no reason given" would be indefensible at an incident — but
nothing in the product displays it, so the answer to that incident is a `sqlite3` prompt.
Honest and disclosable; worth naming in the README trade-offs table rather than leaving
implied. *Urgent when: the audit trail is offered to anyone as a feature.*

**`persist` refusing is a decision inside a module whose docstring says it makes none.**
ADR-0011 puts the refusal in `app/storage.py` while `app/storage.py` and ADR-0008 both
say that module decides nothing — which is why `rentals` SQL was kept out of it. The
tests pin the ADR's behaviour, not the docstring's claim, so this is a wording conflict
rather than a bug. The alternative placement (refuse in `scripts/seed.py`, next to where
the seed id 7 rental is written) would leave a caller who imports `persist` directly
unprotected, and the belt for that is `PRAGMA foreign_keys=ON`. *Urgent when: a third
caller of `persist` appears, or `PROJECT_SPEC.md` is written.*

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
constraint to the thing depending on it — but it drifts if that test is renamed. The
test now exists under that exact name, in `tests/test_rental_concurrency.py`, so the
reference resolves. *No longer overdue; delete this entry if the name outlives the
phase.*

**`test_ordinary_rent_and_return_write_no_audit_event` is vacuously true until rent and
return exist.** "These verbs wrote nothing" holds trivially of verbs that did not run,
so what keeps it red today is its precondition and its control rather than its headline
assertion. That is the correct shape for a negative claim, but it means the test is
weaker evidence than its siblings until Slice A is green. *Urgent when: Slice A goes
green — re-read the failure output once, and confirm the control is what would catch a
regression.*

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

**Phase 1's admin verbs are not wired to `audit_events`.** ADR-0010 builds one table for
admin overrides and Phase 2 writes only its own two actions into it — role changes and
account deletions from Phase 1 stay unrecorded. Deliberately *not* backfilled: retro-writing
events that were never observed would be fabricating an audit trail, which is worse than a
disclosable gap. Wiring them going forward is a small change (two `_enforce`-adjacent call
sites in `app/main.py`) and the table is already shaped for it — `item_id` and `rental_id`
are both nullable, so an account-scoped event fits without a migration. *Urgent when: the
audit trail is ever presented as complete, or Phase 3 needs an actor on a finding.*

**`PRAGMA foreign_keys=ON` if Slice A slips.** ADR-0011 layers three protections over rental
data and the pragma is the belt behind the other two, not the mechanism — `persist` refusing
and the `delete_item` guard are what actually stop the loss. If Phase 2 runs short, the
pragma is the one of the three that can be dropped without leaving a reachable path to
orphaned rentals, because both reachable paths are guarded above it. Dropping it means the
declared FKs stay documentation. *Urgent when: a fourth write path to `hardware` appears
that nobody remembers to guard.*

## Phase 2 UI — found while building slice C

**The add-hardware dialog still has the focus bug that `ReasonDialog` just fixed.**
`autofocus` is honoured on page load, not when an element is inserted later, so opening
either dialog left focus on the button that opened it and typing went nowhere — found by
driving the browser, not by reading the code. `ReasonDialog` now focuses explicitly on
open and handles `Escape`; `AdminPanel`'s add-hardware dialog does neither. *Urgent when:
the next time anybody uses the admin panel by keyboard, which is how an internal tool gets
used all day.*

**`close_kind` is recorded and never shown.** ADR-0007 added the column specifically so
`My Rentals` could say "recalled by an admin" rather than showing an item silently gone,
and slice C shows neither — a returned item just disappears from the list. The data is
there; the surface is not. *Urgent when: the first time an admin recalls something and the
employee asks where it went.*

**Every action refetches the whole world.** `act()` reloads the inventory, My Rentals and
the account list after each mutation — three requests per click, on eleven rows. Correct
and wasteful, and it is why the UI has no optimistic state to get wrong. *Urgent when: the
inventory outgrows one page, at which point the refetch and the pagination question arrive
together.*

**`?held_by=me` has no `held_by=someone-else` counterpart, deliberately.** An admin cannot
ask "what is Novak holding" through the API; they can only read it off the dashboard's
renter column. The parameter is a closed enum for that reason (see
`tests/test_held_by_filter.py`). *Urgent when: offboarding needs "everything this person
has", which is a real workflow and a different authorization question.*

**The demo reset deletes the audit trail, which ADR-0010 exists to protect.** `POST
/api/admin/reset-demo` clears `audit_events` along with `rentals`, and it has to — a trail
referencing rental ids that no longer exist describes events that did not happen. But it
means the one route that most needs an audit record is the one that erases them, and
nothing anywhere records that a reset occurred. Defensible on a demo instance whose whole
purpose is being restored, and indefensible on anything else. *Urgent when: this codebase
is ever pointed at data somebody depends on — at which point the route should be gated on
`ENVIRONMENT != production`, or should write its own event to a table it does not clear.*


## Phase 2 — `architecture-scout` at the gate

**The last-admin guard is check-then-act and a race defeats it.** `ensure_an_admin_remains`
reads `count_admins()`; the `set_role` or `delete_account` that acts on the answer is a
separate statement. Two concurrent demotions of the final two admins both read `2`, both
pass, and both write — reproduced, `200` and `200`, zero live admins afterwards. ADR-0005
is amended to say so.

The fix is already in the codebase's vocabulary: ADR-0008 settles that a read-then-decide
guard cannot win a race and puts the claim in a conditional `UPDATE` whose rowcount is the
decision. Here that is
`UPDATE users SET role='user' WHERE id=:id AND (SELECT count(*) FROM users WHERE role='admin' AND deleted_at IS NULL) > 1`,
in `guards.py` and `accounts.py` and nowhere else. *Urgent when: more than one person
administers the instance, or Phase 3's production-hardening pass — whichever comes first.
Not before: the trigger is two simultaneous demotions on a two-admin internal tool.*

**`rentals.rent`'s honest failure message is choreography, not interface.** `rent()` raises
a generic "already in use" on any rowcount-0, and the route rolls back, re-reads the item
and re-runs `ensure_item_is_rentable` to recover the real cause — Repair, needs review, or
genuinely held. Deliberate (ADR-0008: reading first deadlocks six concurrent claimants),
but it means "how to get a truthful rent-failure message" is a dance a caller must
reproduce rather than something the module hands over. One caller today, so nothing is
duplicated. *Urgent when: a second caller appears — Phase 3's semantic search returning
rentable items is the likely one.*

**The boot sequence is ~90 lines inside `create_app`.** Schema creation, migration, seed,
rental reconciliation, admin bootstrap, demo bootstrap, token backfill. `app/main.py` at
702 lines is otherwise legitimate composition — fifteen thin routes over deep modules, not
a God object — and this is the one seam that is a real boundary rather than arbitrary
file-splitting. *Urgent when: never, on payoff alone. Do it only if boot grows a step that
needs its own test.*


## Phase 2 — `mvp-reviewer` at the gate

**`chore(phase-2): deploy v2` (`3bce364`) ships production code under a `chore` label.**
The reconcile fix and the seed backfill ride a commit whose type says "no production
change". The history cannot be rewritten honestly now; the rule going forward is that a
deploy commit that needs a code change is two commits. *Urgent when: Phase 3's deploy
commit — the moment the same temptation recurs.*

**`clear-review` is only ever tested against an `Available` item.** The route allows
clearing whatever the item's status (`app/main.py`), and ADR-0010 says so, but no test
pins it — a regression that quietly restricted clearing to `Available` items would be
green. One test clearing a flagged `Repair` item covers the claim. *Urgent when: anyone
touches the clear-review route or the guard layer it deliberately bypasses.*


## Phase 3 — the red pass (test-author)

**"Off-enum kinds are dropped *and counted*" has no surface in the spec.**
`docs/specs/phase-3.md` says the count exists but names no field, so
`test_auditor_drops_off_enum_finding_kinds` pins the drop and not the count — an
implementation that discards silently is green. *Urgent when: the audit response shape is
settled; add `{"dropped": n}` to the spec table and one assertion.*

**The LLM seam is fixed by a test module, not by an ADR.** `tests/llm_seam.py` decides
that the key is read from `os.environ` at request time and that the client lives at
`app.state.llm` — the spec fixes only "server-side, read at request time". Same shape as
`conftest.py` fixing the HTTP contract in Phase 1, and recorded here for the same reason.
*Urgent when: a second consumer of the model appears, or the seam moves into `Settings`.*

**`test_auditor_flags_misspelled_brand` (id 9, `"Appel"`) was cut at the 12-test cap.**
ADR-0002's deferred typo therefore still has no test closing the loop; the
`probable_misspelling` member of the enum is exercised by nothing. Plumbing-identical to
`test_auditor_flags_unidentifiable_item`. *Urgent when: the cap lifts, or before the phase
gate if ADR-0002's closure is claimed in the README.*

**Slice C has no tests.** The six named in the spec (`flag-review`) were out of the
red pass's scope. If Slice C ships, it ships untested unless a second red pass runs
first. *Urgent when: Slice C is not cut.*

---

## Deploy trigger — found at the v3 deploy

**The Railway service's GitHub trigger tracks the Phase 0 branch.** A branch push has
not deployed anything since Phase 0 ended; every phase since has shipped through some
other path, and the stale trigger sat harmless until 2026-08-07, when attaching
`GEMINI_API_KEY` made Railway redeploy its configured source — putting v0 (no auth,
open read surface) on the public URL for ~4 minutes until a `railway up` replaced it.
The CLI cannot change the tracked branch; the dashboard can. *Urgent when: anyone
touches a variable, which is why CLAUDE.md now orders a `railway up` after every
variable change — and permanently fixed only by pointing the trigger at `main` in the
dashboard, a human-only action.*

---

## Phase 3 — `mvp-reviewer` at the gate

**A valid-but-empty filter returns the whole catalogue labelled `semantic`, pinned by
no test.** Observed live (the oracle probe's zero-selectivity answer, n=12). Correct
behaviour — the model legitimately said "no constraints" — but nothing asserts it, so
a regression that errored on `{}` or mislabelled it would be green. *Urgent when: the
search route or `parse_filter` is next touched.*

## Phase 4 schema slice — non-blocking

- **`date_added` is not pinned as server-owned.** The scope says "defaults to now on
  create" but names no test for a caller supplying it. If `NewHardware` grows a
  `date_added` field, an admin could backdate an item and the "recently added" sort
  becomes editable. One test would close it; left out because the scope did not name it.
- **No `docs/specs/phase-4.md`.** Phases 2 and 3 have one; the schema slice was written
  from the brainstorm section quoted in the task. Worth writing the spec file before the
  UI slice, so the reviewer has the same contract the tests do.

**Sorting is client-side, and the server's `?sort` parameter now has no caller.** Phase 4
gives every sortable column both directions, including alphabetical on name and brand.
`SortKey` has one member (`purchase_date`) and no `order`, so doing that server-side meant
four new behaviours and the tests to pin them; at eleven rows the browser sorts for free
and gives instant reordering with no round trip. Both are kept deliberately: the
client-side sort is what the UI uses, and the server parameter stays implemented and
tested because it is the path that scales — sorting in the browser stops being free the
moment the inventory outgrows one response.

The cost is honest API surface without a caller: `GET /api/hardware?sort=purchase_date`
works, is tested, and nothing in the product calls it. *Urgent when: the inventory needs
pagination — at which point sorting has to move back to the server, and the parameter is
already there and already proven.*

## Suite wall time — two findings, only one of them understood

**Absolute cost: probably `scrypt`, and this is a hypothesis rather than a measurement.**
`SCRYPT_N = 2**14` costs roughly 50 ms per hash, and a typical test pays for several —
`admin_client`, `user_client` and `other_user_client` each create an account and log in,
and every `create_app` runs `bootstrap_admin` plus `bootstrap_demo`. `--durations` shows no
pathological case: the slowest test is 1.46 s, the top six total under 6 s, and the
remaining ~50 s is spread at roughly 0.3 s across 152 tests. Four of those top six are
`setup`, which is consistent with fixture hashing. **Nobody has measured it.** The fix, if
it turns out to matter, is a lower work factor **under test only** — never in production,
where the cost is the entire point (ADR-0013's threat model is a stolen database file).
*Urgent when: the suite is slow enough to stop being run, which is the only cost that
counts.*

**The regression: unexplained, and it should stay written down as unexplained.** The suite
held ~19 s for most of the session, then ran 82 s, then 56 s, with nothing recent touching
the backend and the same 152 tests passing throughout. A stray `uvicorn` was offered as the
cause and was not one — it was a single process at 0.1 % CPU, which cannot produce a 4×
slowdown.

**The pattern is what makes this worth a backlog entry rather than a shrug.** This is the
third unexplained slowdown in this project. One earlier case was misattributed to a stray
process and turned out to be iCloud materialising files. So a plausible local explanation
has now been wrong twice here, which is enough to treat "I can think of a reason" as
insufficient evidence in this repository specifically. *Urgent when: it recurs — and the
first move is a measurement (time one fixture, compare a cold and warm run) rather than a
story.*

**The flagged branch of the Actions column is visually unverified.** The uniform-size pass
gives a flagged row an amber `!` at the same 96×32 as the `Rent` button, and the markup is
in `HardwareTable.vue` — but no screenshot shows it, because both flagged rows on the local
scratch database had been released during earlier testing. Every other branch of that cell
was confirmed on screen: `Rent`, the grey `Rented`, and the empty `In Repair`. The
deployment verification against a freshly reset live instance covers it, since a reset
restores ids 6 and 10 as flagged. *Urgent when: the v4 deploy is verified — and if the
`!` is the wrong size there, this entry is why nobody caught it earlier.*

---

## Over-engineering audit (2026-08-07, unapplied)

A read-only `/ponytail-audit` pass at submission, ranked by how much a reviewer would
notice. Nothing here was applied; each entry records what it is, why it is more than
the task needs, what it would become, and the condition that would make the cut worth
taking.

1. **The documentation outweighs the code four to one** (~11,800 lines of markdown,
   ~3,000 of production code). More than the task needs in any product repo, where
   PROMPT_TRAIL, brainstorm.md and the three phase specs would become links in one
   README paragraph. It stands here because the brief grades exactly these artifacts.
   *Worth doing when: this repo stops being a submission and starts being a product.*
2. **Seven synthesized notification voices with a music-theory ADR** (sound.js,
   ADR-0018): interval families and a tritone pair, in an internal CRUD tool. Declared
   elective and argued, but it is the loudest beyond-scope artifact here. Would become:
   nothing. *Worth doing when: never, unless a brief grades delight.*
3. **The deploy contract is implemented twice**: the same four assertions as pytest
   (`test_smoke_deployed.py`, admin credentials, human gate) and as bash (`probe.sh`,
   demo credentials, cron). Would become: one implementation serving both callers.
   *Worth doing when: the assertions next change and someone has to update both.*
4. **The server-side `?sort` path has no caller**: `SortKey`, the query parameter and
   the order-by branch in `load_items` serve nobody since Phase 4 sorted client-side.
   The README owns this deliberately as the path that scales. Would become: ~25 fewer
   lines. *Worth doing when: pagination arrives and the parameter grows a caller, or
   when it is clear it never will.*
5. **`rental_count` is dead** (`app/rentals.py`): exported, called by nothing; the
   ADR-0011 refusal runs its own `SELECT 1 LIMIT 1`. Would become: nothing, ~8 lines.
   *Worth doing when: next touching the file.*
6. **`_call` accepts four client spellings** (`app/ai.py`) and the test fake defines
   all four because the production code accepts them; each side exists to satisfy the
   other. Would become: `__call__` only, ~12 lines across both files. *Worth doing
   when: a second real provider appears and settles the interface.*
7. **`ResponseCache` is a class wrapping two dicts** with no methods (`app/ai.py`).
   Would become: two plain dicts on `app.state`. *Worth doing when: next touching the
   AI layer.*
8. **The 15-field `HardwareItem` row-mapper exists twice**, identically, in
   `storage.load_items` and `ai._items`. Would become: one shared mapper, ~18 lines.
   *Worth doing when: the next column addition forces editing both and one gets
   missed.*
9. **The Phase 4 schema trio** (`serial_number`, `category`, `date_added`) and the
   five-value `Category` enum: nullable everywhere, null in every seed row, populated
   only by hand-added items. Wireframe-driven scope beyond the data. Would become:
   nothing lost today. *Worth doing when: never remove; fills itself when real data
   arrives.*
10. **`PRECEDENCE` as a chain of lambdas** (`displayState.js`) where `if/elif` reads
    the same in half the lines. *Worth doing when: next touching the file.*
11. **`set_status` duplicates `edit_item`** (`app/storage.py`): the general updater
    already covers the specific one. Would become: one row-mover, ~10 lines. *Worth
    doing when: next touching the file.*

Not findings, for the record: the dependency list is already at the floor (three
runtime, two dev, one frontend), and `sessions.py` hand-rolling HMAC from the standard
library instead of importing a signing dependency is the lazy-correct choice, not a
gap. The guards, quarantine and audit trail were checked against their ADRs and against
the incidents that motivated them; they are proportionate.

**Verdict:** for what it does, the production code is not over-built — the deps are
minimal, the modules are thin, and the heavy machinery traces to real incidents; the
over-build lives at the edges (a dead sort path, a twice-written deploy check) and,
most visibly, in the elective Phase 4 polish and the documentation mass, both of which
this brief happens to grade and any other repo would cut first.
