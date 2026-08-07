# Hardware Hub

Internal tool for Booksy employees to manage, rent and maintain company equipment.
Built as a recruitment task for the Early Careers Programme.

**Stack:** FastAPI · SQLite · Vue 3 + Vite · deployed on Railway
**Method:** TDD, branch per phase, human review gate between versions

---

## Live versions

**v0–v3 deliver the brief in full** — the three pillars are the inventory and its dirty
seed (v0), auth with roles and the admin surface (v1), the rental engine with its guards
and audit trail (v2), and the AI layer (v3). **v4 is elective**: UI fidelity to the
supplied wireframes, dark mode, notification sounds and an accessibility audit. It is work
beyond the brief's scope, taken on because the wireframes were supplied and a close copy
is checkable in a way "looks fine" is not. Read v0–v3 as the submission; read v4 as what
was done with the time left.

| Version | Phase | URL | Status |
| --- | --- | --- | --- |
| v0 | Phase 0 — foundation, data audit, first deploy | *(superseded by v1 on the same URL)* | ✅ shipped |
| v1 | Phase 1 — auth, admin, dashboard | *(superseded by v2 on the same URL)* | ✅ shipped |
| v2 | Phase 2 — rental engine, review queue, audit trail | *(superseded by v3 on the same URL)* | ✅ shipped |
| **v3** | Phase 3 — semantic search, Inventory Auditor, flag-review | https://hardware-hub-production-24b7.up.railway.app | ✅ live |
| v4 | Phase 4 — wireframe fidelity | — | 🔮 planned, after v3 |

### Signing in

The Hub admits only admin-created accounts — there is no public read surface and no
self-registration (ADR-0006). A demo account is published so the live version can be
opened in ten seconds:

| | |
| --- | --- |
| **Email** | `demo@booksy.com` |
| **Password** | `hardware-hub-demo` |
| **Role** | `user` — read-only. Every admin route answers `403` to it |

It is created at boot on a database with no accounts — the same emptiness guard the
hardware seed uses — so replacing the volume cannot leave these credentials pointing at
nothing. Deleting it deliberately keeps it deleted; a restart does not resurrect it.

This is a separate account from the deployment's own bootstrap admin, whose credential
stays in Railway's environment and is not published (ADR-0005).

### Restoring the demo

Demonstrating the live instance consumes it: renting an item, recalling item 7 or clearing
a flag all change the rows the project is *about*. `docs/DATA_AUDIT.md` describes those
rows, and Phase 3's Inventory Auditor needs the seed's contradictions intact — so putting
them back is one repeatable action, not a story about a database somebody edited.

Signed in as the bootstrap admin (not the demo account, which is read-only):

```bash
curl -X POST "$URL/api/admin/reset-demo" \
  -H 'Content-Type: application/json' \
  -b cookies.txt \
  -d '{"confirm": "reset the demo data"}'
```

The confirmation phrase is typed in full on purpose. The route deletes rental history,
and a bare `POST` that fires on the first request is one mistyped URL away from wiping
what ADR-0011 exists to protect.

**It clears the blocker rather than bypassing it.** ADR-0011 has `persist` refuse while
rentals exist, and that refusal stays: the reset deletes rentals and audit events *first*,
then reseeds through the same guard every other caller meets. A `force=True` on `persist`
would have removed the protection for all of them.

It is an HTTP route rather than a CLI because Railway exposes no exec or SSH — the same
constraint that put seeding on the boot path. Afterwards the fingerprints are back: 11
items, ids 6 and 10 flagged, item 7 held by `j.doe@booksy.com`, id 12 re-keyed from the
duplicate, the `Appel` typo intact, and 3 quarantine records.

**It is deliberately not an admin.** It was, until `/security-review` pointed out that
publishing an admin credential on a public instance hands every reader delete rights
over the inventory and the account list. Read access shows the dashboard, the review
queue and the whole seed including its defects; the admin panel is described in
[`docs/WIREFRAME_JUSTIFICATION.md`](docs/WIREFRAME_JUSTIFICATION.md) and is reachable by
anyone running it locally, where `ADMIN_EMAIL` / `ADMIN_PASSWORD` default to
`admin@booksy.com` / `admin`.

---

## Status

### ✅ Fully Implemented

- Seed ingestion: structural validation, quarantine with reasons, nothing deleted
- SQLite persistence with caller-owned transactions and replace-semantics reseed
- **Session-cookie auth** — `scrypt` with a per-account salt, `HttpOnly`,
  `SameSite=Lax`, `Secure` in production; the password digest cannot leave
  `app/accounts.py` because `Account` has no field for it
- **`admin` / `user` roles**, enforced by per-route dependencies — `401` without a
  session, `403` with one that is not enough
- **No public read surface** — every data route needs a session (ADR-0006)
- **The zero-admin guard** (ADR-0005), covering deletion *and* demotion, `409` with a
  readable reason, in `app/guards.py` alongside where Phase 2's rental guards go
- **Admin panel** — add and delete hardware, toggle `Repair` both ways, create
  accounts, promote and demote
- **Dashboard** — dense table, status filter and purchase-date sort, both server-side
- **The rental engine** — rent, return, and admin force-return. The claim is one
  conditional `UPDATE` whose rowcount is the decision (ADR-0008), so two concurrent
  claimants cannot both win; `Repair` and `needs_review` both block through the same
  guard with a `409` (ADR-0003)
- **`needs_review` queue, now with release** — every flagged item with the reason
  ingestion recorded, and an admin action that clears the flag, `409` on an unflagged
  item (ADR-0003)
- **Audit trail** — force-return and clear-review each write an `audit_events` row
  with a mandatory reason, in the same transaction as the change; the transition
  itself writes it, so no caller can perform the override silently (ADR-0010)
- **Field-level authorization** — `notes`, `history` and `review_reason` reach admins
  only; a `user` session gets `null` (ADR-0012, closing the `/security-review`
  finding Phase 1 carried)
- **`?held_by=me`** — the dashboard's "My Rentals" view, server-side
- **Demo reset** — one confirmed admin route restores the seed's fingerprints
  (see "Restoring the demo" above)
- **Semantic search** — natural language → schema-validated filter object → SQLite
  (ADR-0004); the model cannot hallucinate inventory, the filter has no predicate
  over restricted fields for anyone (ADR-0015), and every response is labelled
  `semantic` or `keyword` so the fallback cannot pass as the primary (ADR-0016)
- **The Inventory Auditor** — closed finding kinds, proposes and never disposes
  (ADR-0014), admin-only, computed per run and persisted nowhere; refuses with a
  `503` rather than degrading, because a keyword auditor cannot find id 10
- **The flag-review verb** — a human acts on a finding: mandatory reason, audit
  event, `409` when already flagged (ADR-0017); the loop ADR-0002 opened is closed
  end to end — ingestion declined to judge, the auditor judges, an admin decides.
  **How anything enters review after import** (the full chain, since ingestion flags
  only at import, the add form neither flags nor validates semantics, and the auditor cannot
  flag by design): *auditor proposes → admin flags → item unrentable (`409`) → admin
  later clears, with a reason recorded at both ends.* Phase 4 tightens the clearing
  reason to a mandatory `fixed:` note — what changed, not merely that somebody looked
- **Health endpoint** — `GET /api/health`, sessionless by design, touches nothing
- Single origin: one service, one URL, no CORS (ADR-0001)
- **Phase 4, elective** — the schema trio (`serial_number`, `category`, `date_added`)
  with a migration test that boots over the previous table shape; wireframe-fidelity
  finish with uniform action controls and fixed column widths; **dark mode**, opt-in and
  persisted, light by default so a reviewer sees what the wireframe shows; **six
  notification sounds** as one family, off by default (ADR-0018); admin edit and a review
  release that carries the change it certifies (ADR-0017 as amended); and a measured
  **WCAG contrast audit** — [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md)
- 152 tests, all green

### ⚡ Shortcuts & Hacks

Each of these works, and each cost something. The full table with reasoning is in
[Trade-offs taken](#trade-offs-taken) below.

- **The wireframes are not committed.** They stay on the local machine, gitignored,
  and [`docs/WIREFRAME_JUSTIFICATION.md`](docs/WIREFRAME_JUSTIFICATION.md) describes
  every deviation in prose — including what the original showed — so it can be
  judged without them.
  **Why:** they are Booksy's material, the brief marks them confidential, and this
  repository is public.
  **Future:** in a private or internal repo the images would be committed alongside
  the justification doc. The prose-only form exists solely because this one is
  public.
- **Demo credentials are published, on a `user` account, on a public instance.**
  Anyone reading this can sign in and read the inventory.
  **Why:** ADR-0005 chose openly published demo credentials so a reviewer is in within
  ten seconds. `/security-review` then cut the role from `admin` to `user`, because read
  access is what a reviewer needs and delete rights are what an attacker wants.
  **Future:** per-reviewer invite links, so access can be withdrawn without rotating a
  shared credential.
- **The AI layer runs on Gemini's free tier, which rate-limits.** A burst of
  searches or audits can hit the quota ceiling mid-demo.
  **Why:** a paid tier for a recruitment demo buys nothing the design doesn't
  already handle — the announced keyword fallback (ADR-0016) means a rate-limited
  search *degrades visibly* rather than breaking, which is the design working, not
  failing; and the model's replies are cached (search by normalised query, the
  auditor by catalogue fingerprint), so repeats cost no quota at all.
  **Future:** a paid tier or a second provider behind the same seam; the cache and
  the mode label both carry over unchanged.
- **Semantic search waits up to 12 seconds before degrading.** The spec said 5; the
  live provider spends ~7.5s thinking before emitting one small filter object and
  rejects its thinking-off knob with an opaque 400.
  **Why:** a slower true answer with an honest label beats a fast one that is always
  the fallback — under 5s the semantic path literally never answered, which the mode
  chip made visible on the first live check.
  **Future:** a provider or endpoint tier with sub-second extraction latency, or a
  streaming call that can be cut off at the first complete JSON object.
- **Deploys go through `railway up`, not the GitHub trigger.** The service still
  tracks the Phase 0 branch, so a push deploys nothing — and a variable change
  redeploys v0, which briefly put an unauthenticated build back on the public URL
  (AI_LOG Correction #5).
  **Why:** the trigger's tracked branch can only be changed in the dashboard, which
  is a human-only action that has not happened yet; `railway up` ships the current
  checkout deterministically in the meantime.
  **Future:** point the trigger at `main` in the dashboard, then delete this entry
  and the CLAUDE.md warning that orders a `railway up` after every variable change.
- **41 commits against a 15–20 target.** The target is in `CLAUDE.md` and this is
  double it, so it is acknowledged here rather than left for a reviewer to count.
  **Why:** two security fixes (the demo account's role cut from `admin` to `user`, the
  session-revocation gap ADR-0013 closed) and two production defects (the seed rental
  never reconciling on an existing volume, the missing `users` migration) each needed
  their own red/green cycle — a fix squashed into an unrelated commit is a fix the
  history cannot explain. Every commit has its AI_LOG entry; the count is the cost of
  keeping that true.
  **Future:** nothing to fix retroactively — rewriting history to hit a number would
  be worse than missing it. The target stands for Phase 3 as a pressure toward
  batching, not a cap that outranks the audit trail.
- **A soft-deleted account permanently reserves its email**, so an address can never be
  recreated — no re-hires, and no fixing a typo'd address. Recreating one answers `409`.
  **Why:** the audit trail names actors by email as well as by id (ADR-0010, ADR-0013),
  and reusing an address rebuilds the same ambiguity the soft delete removed, one field
  over: a decision recorded against `j.doe@booksy.com` would start describing whoever
  holds that address next.
  **Future:** a distinct archived-identity table, or scoping the uniqueness constraint to
  non-deleted rows with the trail keyed on the immutable session token instead of the
  address.
- **Sign out is client-side only.** It drops the app's state and returns to the login
  screen; the cookie itself is not revoked, because there is no logout route.
  **Why:** stateless sessions were the cheap correct thing for one process. Deleting the
  *account* does now revoke its sessions properly (ADR-0013) — what is missing is ending
  one session without retiring the person.
  **Future:** a logout route plus session expiry.
- **Sorting is client-side, and the server's `?sort` parameter has no caller.** Phase 4
  gives every sortable column both directions, in the browser.
  **Why:** `SortKey` has one member and no direction, so doing it server-side meant four
  new behaviours and the tests to pin them; at eleven rows the browser reorders instantly
  with no round trip. The server path stays implemented and tested because it is the one
  that scales.
  **Future:** move sorting back to the endpoint when the inventory needs pagination — the
  parameter is already there and already proven.
- **The frontend has no tests.** vitest is still not set up, and the UI now carries
  real logic: a roving-tabindex table, the `401`-to-login-screen path, filter counts.
  **Why:** time, and the Python suite covers the contract the UI consumes.
  **Future:** vitest over the table's keyboard behaviour and the api client's `401`
  handling, both of which are logic rather than markup.
- **The app seeds itself on boot when the database is empty.** A deploy shim, not a
  migration strategy. Admin bootstrap now rides the same path, though it is idempotent
  and additive rather than destructive.
  **Why:** Railway offered no way to run a one-off command against the mounted volume —
  no exec, no SSH, `preDeployCommand` silently did not run. The emptiness guard is what
  makes it safe: once rentals exist the table is never empty, so a restart cannot wipe
  them.
  **Future:** a migration step or a one-off job. Boot logic should not write data.

### ⚠️ Partial / Missing

- Editing an item's name, brand or date — only status changes and deletion exist
- **Post-import data is validated structurally, not semantically** — a manually added
  item with a 2027 purchase date is caught by nothing: ingestion only sees the seed,
  the add form checks shape, and the auditor's closed enum has no future-date kind
  (mvp-reviewer, Phase 3 gate; live item 14 is the proof)
- **`flag-review` shares the last-admin guard's read-then-write race** — two
  concurrent flags both pass the `409` check and write two audit events; same
  documented class as below, same conditional-`UPDATE` fix when it matters
- **The last-admin guard is not race-safe** — it reads the admin count and writes in a
  separate statement, so two simultaneous demotions of the final two admins both pass and
  reach zero live admins. Reproduced, documented in ADR-0005, and deliberately not fixed:
  the trigger is concurrent demotions on a two-admin internal tool, and ADR-0008's
  conditional-`UPDATE` pattern is the known fix when it matters
- **Nothing detects a deployment serving a stale build.** The live instance was found
  serving a **Phase 0 image** — no authentication, the whole inventory readable
  anonymously, including the `notes` and `history` ADR-0006 exists to protect. It was
  caught by a manual query during an unrelated check; the suite passes against source, and
  the health endpoint that would have failed did not exist in the rolled-back image. Fixed
  by redeploying, but the gap is the detection, not the incident: no smoke check runs
  against the deployed URL after a deploy, so the next rollback is equally invisible. See
  `AI_LOG.md` Correction #6
- Logout, session expiry, login throttling — no route ends a session, and the signed
  cookie has no server-side record to revoke
- CI and vitest
- `test_auditor_flags_misspelled_brand` (id 9, `"Appel"`) — cut under the red-pass
  test cap as plumbing-identical to id 10's test; ADR-0002's typo loop is exercised
  live rather than pinned in the suite. See `BACKLOG.md`

Carried over from `/security-review` as accepted rather than fixed, each with the reason
(the field-level authorization finding that used to lead this list is closed —
ADR-0012 shipped role-aware serialisation in Phase 2):

- **`ENVIRONMENT` fails open, not closed** — any value other than `production` falls
  back to development defaults, including a `SECRET_KEY` that is public in this repo.
  Not fixed because the live service sets `ENVIRONMENT=production`, verified by the
  session cookie coming back `Secure` — a flag only set on that branch — so this is
  hardening against an operator slip rather than an open door.
- **No per-user-salt test** — `app/accounts.py` salts every hash and nothing asserts
  that two accounts sharing a password store different digests. Not fixed because it is
  a missing test rather than a defect, and it belongs in a `test:` commit.

### 🔮 Next Steps (24h Roadmap)

1. **CI and the frontend test suite** — a workflow running both build steps and both
   suites, and vitest over the table's keyboard behaviour and the api client's `401`
   handling. The two oldest ⚠️ entries, and the ones a reviewer hits first.
2. **Logout and session expiry** — the remaining half of the session story: ending
   one session without retiring the account.
3. **A user-facing "report an issue" path on return** — the last open loop in the
   lifecycle, and the seed names it. Item 11's history reads *"Returned by user with
   liquid damage. Keyboard sticky."* — an event this application could not have
   produced. Only ingestion and admins can raise a flag, so an employee handing back a
   damaged laptop has no way to say so; the note exists because somebody typed it into
   a system that is not this one.

   The report would **propose, never flag** — the same boundary ADR-0014 draws for the
   auditor, and for the same reason: the person reporting is not the person accountable
   for taking equipment out of service. An admin confirms it into `needs_review`, which
   is the existing verb with the existing audit row.

   That closes the loop end to end: **ingestion judges structure** (ADR-0002),
   **the auditor judges prose** (ADR-0014), **admins decide** (ADR-0017) — and users,
   who are the only ones who actually handle the equipment, currently cannot speak at
   all. It is the one participant the design has no channel for, and the seed noticed
   before we did.

4. **Final polish** — one `docs:` commit on `main`: README read-through, empty
   states, favicon, and the remaining `(pending)` SHA back-annotations in
   `AI_LOG.md`.

Then **Phase 4 — wireframe fidelity** (planned 2026-08-07, does not start until
Phase 3 ships): the UI becomes a close copy of the supplied wireframes — heading and
label changes, the review badge, exact type scale, the Add New Device modal, three
new schema columns with their migration test, and muteable notification sounds. Scope
in `brainstorm.md` §3 Phase 4.

That plan also contained an ADR-0012 amendment hiding renter identity from non-admins.
**It was withdrawn and never built**: it contradicted ADR-0012's own reasoning and would
have turned `test_renter_identity_is_visible_to_every_signed_in_user` red. ADR-0012 stands
unamended, the server is unchanged, and the holder is still served to every signed-in
account — Phase 4 only moved it off the row and onto the `Rented` control
(`docs/WIREFRAME_JUSTIFICATION.md`).

---

## Running it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cd frontend && npm install && npm run build && cd ..

.venv/bin/python -m scripts.seed
.venv/bin/python -m uvicorn app.main:create_app --factory --reload
```

Then open http://127.0.0.1:8000.

With no environment set, the app runs in development mode with defaults. Production
is strict — see ADR-0005.

### The commit gate

One line, and a fresh clone needs it:

```bash
git config core.hooksPath hooks
```

`hooks/pre-commit` refuses any commit that does not stage `AI_LOG.md`, and prints which
of the two formats to use. The log is a graded deliverable and it cannot be reconstructed
honestly after the fact — an audit at the Phase 1 gate found 24 commits against 22
entries, and one gap had to be backfilled and labelled as backfilled. The hook exists
because the convention held only as long as somebody remembered it.

The hook lives in `hooks/` rather than `.git/hooks/` precisely so it survives a clone.
`git commit --no-verify` bypasses it, deliberately.

### Tests

```bash
cd frontend && npm run build && cd ..   # test_serves_built_bundle_at_root needs the real bundle
.venv/bin/python -m pytest
```

### Reseeding

`persist` has replace semantics — seeding twice leaves the database exactly as seeding
once did — but since Phase 2 it **refuses to run while rentals exist** (ADR-0011),
because replace semantics against a live rental table is how history gets erased by a
maintenance command. On any instance that has been used, reseed through the demo reset
route, which deletes rentals and audit events first and then passes the same guard:
see [Restoring the demo](#restoring-the-demo).

On a database with no rentals, the direct form still works locally:

```bash
.venv/bin/python -m scripts.seed
```

---

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | no | `production` turns on the strict checks below. Anything else, including unset, is permissive with development defaults. |
| `SECRET_KEY` | in production | The app refuses to boot without it. |
| `ADMIN_PASSWORD` | in production | Same. Booting without it reaches the zero-admin state the guard layer exists to prevent (ADR-0005). |
| `ADMIN_EMAIL` | no | Defaults to a development address. |
| `DATABASE_URL` | no | Defaults to a local SQLite file. On Railway it points at the persistent volume. |
| `GEMINI_API_KEY` | no | Enables the AI layer. Absent: search runs keyword-labelled and the auditor answers `503` with the reason — feature-off, never a boot refusal (ADR-0016). Read per request, so *rotating* it needs no redeploy; *adding* it the first time restarts the process (new variable = new environment). |
| `GEMINI_MODEL` | no | Defaults to `gemini-flash-latest`. The pin for anyone who needs one. |

---

## The seed data

`data/seed.json` is the brief's 11 records, committed **verbatim and never
modified** — every defect in it is intentional test input. Ingestion imports 11
hardware items and writes 3 quarantine records. See `docs/DATA_AUDIT.md`.

Ingestion validates **structure only**. Semantic contradictions — the Dell XPS
marked `Available` with notes reading "battery swelling", the MacBook Air with a
history of liquid damage — are deliberately left for the Phase 3 Inventory Auditor
(ADR-0002). **A keyword scan would catch both of those.** The one it would not
catch is record 10: empty brand, null date, `"Unknown"` status, no notes at all —
unidentifiable, and needing a physical audit. That judgement has no keyword
signature, and it is the test of whether the AI layer does anything a regex could
not.

---

## Trade-offs taken

Each of these was a deliberate choice, taken knowingly, with the cost recorded at
the moment it was taken.

| Shortcut | Why | Future refactor |
| --- | --- | --- |
| **Demo credentials are published on a public instance, on a `user` account** | ADR-0005 chose openly published demo credentials so a reviewer is in within ten seconds. `/security-review` cut the role from `admin` to `user`: read access is what a reviewer needs, delete rights are what an attacker wants, and the admin panel is described in prose instead. | Per-reviewer invite links, so access can be withdrawn without rotating a shared credential. |
| **The frontend has no tests** | `brainstorm.md` §3 lists vitest in Phase 0. It was true then that the page was one fetch and a table; it is not true now — the UI has a roving-tabindex table, a `401`-to-login path and filter counts. This is the shortcut that aged worst. | vitest over the keyboard behaviour and the api client, which are logic rather than markup. |
| **`test_serves_built_bundle_at_root` needs `npm run build` first** | It asserts against the real `frontend/dist` on purpose — a fixture directory would prove the mount works, not that the built bundle is served. | CI builds the frontend before running pytest. |
| **No CI** | Time. The tests exist and run locally; automating them was the cut. | A workflow running both build steps and both suites. |
| **The app seeds itself on boot when the database is empty** | The deploy target offers no way to run a one-off command against the mounted volume: Railway's API has no exec or SSH, `preDeployCommand` silently did not run, and `railway ssh` needs an SSH key. Seeding at startup was the only mechanism left. An emptiness guard makes it safe — once rentals exist the table is never empty, so it can never wipe them. | A migration step or a one-off job. Boot logic should not write data. See [`BACKLOG.md`](BACKLOG.md). |
| **Deploying needed three human-in-the-loop steps** | Browser OAuth for the Railway MCP, a *second* browser authorization for the Railway CLI, and an SSH key — none of which any tooling removes. Seed-on-boot-if-empty was chosen partly to delete the manual seeding step for whoever redeploys next. | Nothing to fix in this codebase; recorded because the deploy story is otherwise easy to tell as smoother than it was. |
| **Sign out does not revoke the session** | The session is a signed cookie with no server-side record. There is no logout route, so the control clears the client and says so. Deleting the account *does* revoke its sessions (ADR-0013); ending one session without retiring the person is what is missing. | A logout route and session expiry. A leaked cookie is valid until the account is deleted or `SECRET_KEY` changes. |

Deferred findings that are not shortcuts — interface concerns, spec gaps, things
noticed and consciously not acted on — are in [`BACKLOG.md`](BACKLOG.md), each with
a note on when it becomes urgent.

---

## Documentation

| File | What it is |
| --- | --- |
| [`CONTEXT.md`](CONTEXT.md) | The domain language. Say "quarantine record", not "the row we couldn't import". |
| [`brainstorm.md`](brainstorm.md) | The phased build plan (v2). |
| [`docs/adr/`](docs/adr/) | Architectural decisions, with the reasoning that produced them. |
| [`docs/DATA_AUDIT.md`](docs/DATA_AUDIT.md) | What the seed contained and what ingestion did about it. |
| [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md) | Measured WCAG contrast for every colour pair in both themes, and the one check that does not pass on colour alone. |
| [`BACKLOG.md`](BACKLOG.md) | What is still owed, each with a note on when it becomes urgent. |
| [`docs/WIREFRAME_JUSTIFICATION.md`](docs/WIREFRAME_JUSTIFICATION.md) | Every UI deviation from the supplied wireframes, described in prose — the images are confidential and stay uncommitted. |
| [`AI_LOG.md`](AI_LOG.md) | Every commit, and the corrections where the AI was wrong. |
| [`BACKLOG.md`](BACKLOG.md) | Findings deferred rather than acted on. |
| [`docs/PROMPT_TRAIL.md`](docs/PROMPT_TRAIL.md) | The grilling sessions that settled the plan. |
