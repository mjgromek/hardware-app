# Hardware Hub

Internal tool for Booksy employees to manage, rent and maintain company equipment.
Built as a recruitment task for the Early Careers Programme.

**Stack:** FastAPI · SQLite · Vue 3 + Vite · deployed on Railway
**Method:** TDD, branch per phase, human review gate between versions

---

## Live versions

| Version | Phase | URL | Status |
| --- | --- | --- | --- |
| v0 | Phase 0 — foundation, data audit, first deploy | *(superseded by v1 on the same URL)* | ✅ shipped |
| v1 | Phase 1 — auth, admin, dashboard | *(superseded by v2 on the same URL)* | ✅ shipped |
| **v2** | Phase 2 — rental engine, review queue, audit trail | https://hardware-hub-production-24b7.up.railway.app | ✅ live |
| v3 | Phase 3 — AI layer + hardening | — | 🔮 planned |

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
`admin@localhost` / `admin`.

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
- **`needs_review` queue** — every flagged item with the reason ingestion recorded
  (read-only; see below)
- Single origin: one service, one URL, no CORS (ADR-0001)
- 97 tests, all green

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
- **`needs_review` is surfaced but still cannot be cleared.** The queue now shows every
  flagged item and the reason, and the flag still blocks rental (ADR-0003) — so
  releasing an item is a database edit. The screen says so rather than offering a
  button that would fail.
  **Why:** clearing needs a decision nobody has made — what evidence releases an item,
  and who records it. Inventing it to fill a screen is how an audit trail becomes
  decoration.
  **Future:** Phase 2 owns it — ADR-0003 assigns the mechanism there, because clearing a
  rentability guard is a transition in the rental state machine rather than a field edit.
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
- **The frontend has no tests.** vitest is still not set up, and the UI now carries
  real logic: a roving-tabindex table, the `401`-to-login-screen path, filter counts.
  **Why:** time, and the Python suite covers the contract the UI consumes.
  **Future:** vitest over the table's keyboard behaviour and the api client's `401`
  handling, both of which are logic rather than markup.
- **The app seeds itself on boot when the database is empty.** A deploy shim, not a
  migration strategy — Railway offered no way to run a one-off command against the
  mounted volume. The emptiness guard is what makes it safe. Admin bootstrap now rides
  the same path, though it is idempotent and additive rather than destructive.

### ⚠️ Partial / Missing

- **`needs_review` cannot yet be cleared** — the queue shows every flagged item and the
  reason, and the flag still blocks rental, but nothing releases one. ADR-0003 assigns
  the mechanism to **Phase 2**: an admin action with an audit trail, gated on the same
  guard layer, because clearing a rentability guard is a state-machine transition rather
  than a field edit
- Rental engine — items have statuses but cannot be rented or returned. No `Rent`
  action exists, which is why the wireframe's is absent
- The AI layer — semantic search and the Inventory Auditor. The wireframe's "Ask AI…"
  bar is absent for the same reason
- Editing an item's name, brand or date — only status changes and deletion exist
- Field-level authorization — every signed-in employee sees `notes` and `history`,
  which are admin- and auditor-facing
- **The last-admin guard is not race-safe** — it reads the admin count and writes in a
  separate statement, so two simultaneous demotions of the final two admins both pass and
  reach zero live admins. Reproduced, documented in ADR-0005, and deliberately not fixed:
  the trigger is concurrent demotions on a two-admin internal tool, and ADR-0008's
  conditional-`UPDATE` pattern is the known fix when it matters
- Logout, session expiry, login throttling — no route ends a session, and the signed
  cookie has no server-side record to revoke
- CI, vitest, a health endpoint

Carried over from `/security-review` as accepted rather than fixed, each with the reason:

- **Field-level authorization** — every signed-in employee sees `notes`, `history` and
  `review_reason`. Not fixed because this branch *narrowed* it (the endpoint was
  anonymous before ADR-0006) and what remains is maintenance prose about laptops rather
  than secrets or PII; role-aware serialisation is the real fix and is not a one-liner.
- **`ENVIRONMENT` fails open, not closed** — any value other than `production` falls
  back to development defaults, including a `SECRET_KEY` that is public in this repo.
  Not fixed because the live service sets `ENVIRONMENT=production`, verified by the
  session cookie coming back `Secure` — a flag only set on that branch — so this is
  hardening against an operator slip rather than an open door.
- **No per-user-salt test** — `app/accounts.py` salts every hash and nothing asserts
  that two accounts sharing a password store different digests. Not fixed because it is
  a missing test rather than a defect, and it belongs in a `test:` commit.

### 🔮 Next Steps (24h Roadmap)

In order, one branch and one deployed version each — the phases in the table above:

1. **Phase 2 — rental engine.** Rent and return, with `Repair` and `needs_review`
   blocking through one guard — **and the action that clears that flag**, which ADR-0003
   assigns here because releasing an item is a transition in the same state machine.
   `/grill-me` first, per `CLAUDE.md`.
2. **Phase 3 — AI layer and hardening.** Semantic search and the Inventory Auditor,
   which has to flag record 10 to prove it does anything a regex could not, plus CI
   and the frontend test suite.

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

`persist` has replace semantics: seeding twice leaves the database exactly as
seeding once did, so this is safe to re-run against a live instance.

```bash
railway run --service hardware-hub python -m scripts.seed
```

Locally, the same command without the `railway run` prefix.

---

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | no | `production` turns on the strict checks below. Anything else, including unset, is permissive with development defaults. |
| `SECRET_KEY` | in production | The app refuses to boot without it. |
| `ADMIN_PASSWORD` | in production | Same. Booting without it reaches the zero-admin state the guard layer exists to prevent (ADR-0005). |
| `ADMIN_EMAIL` | no | Defaults to a development address. |
| `DATABASE_URL` | no | Defaults to a local SQLite file. On Railway it points at the persistent volume. |

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
| **`notes` and `history` are visible to every signed-in employee** | The endpoint returns whole items, and ADR-0006 closed the public half of this — a stranger with the URL no longer sees them. Field-level authorization is a separate piece of work that Phase 1 did not do. | Role-aware serialisation, so auditor-facing free text reaches admins only. `/security-review` before the Phase 1 gate. |
| **Nothing can clear `needs_review`** | The queue is surfaced and read-only. Clearing needs a decision nobody had made — what evidence releases an item, and who records it — and inventing one to fill a screen is how an audit trail becomes decoration. | **Phase 2**, by ADR-0003: an admin action with an audit trail, gated on the guard layer, pinned by `test_admin_can_clear_needs_review` and `test_cleared_item_becomes_rentable`. |
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
| [`BACKLOG.md`](BACKLOG.md) | What is still owed, each with a note on when it becomes urgent. |
| [`docs/WIREFRAME_JUSTIFICATION.md`](docs/WIREFRAME_JUSTIFICATION.md) | Every UI deviation from the supplied wireframes, described in prose — the images are confidential and stay uncommitted. |
| [`AI_LOG.md`](AI_LOG.md) | Every commit, and the corrections where the AI was wrong. |
| [`BACKLOG.md`](BACKLOG.md) | Findings deferred rather than acted on. |
| [`docs/PROMPT_TRAIL.md`](docs/PROMPT_TRAIL.md) | The grilling sessions that settled the plan. |
