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
| **v1** | Phase 1 — auth, admin, dashboard | https://hardware-hub-production-24b7.up.railway.app | ✅ live |
| v2 | Phase 2 — rental engine | — | 🔮 planned |
| v3 | Phase 3 — AI layer + hardening | — | 🔮 planned |

### Signing in

The Hub admits only admin-created accounts — there is no public read surface and no
self-registration (ADR-0006). A demo account is published so the live version can be
opened in ten seconds:

| | |
| --- | --- |
| **Email** | `demo@booksy.com` |
| **Password** | `hardware-hub-demo` |
| **Role** | `admin` — so every screen, including the admin panel, is reachable |

This is a separate account from the deployment's own bootstrap admin, whose credential
stays in Railway's environment and is not published (ADR-0005). Publishing a demo
credential on a public instance is a deliberate trade-off, recorded below.

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
- 47 tests, all green

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
- **Demo credentials are published, on an admin account, on a public instance.**
  Anyone reading this can sign in and delete inventory.
  **Why:** a reviewer opening the live version in ten seconds is worth more than
  credential hygiene on a throwaway instance, and ADR-0005 chose that openly. The
  deployment's own bootstrap admin is a separate account and its credential is not
  published.
  **Future:** a read-only demo role, or a per-reviewer invite link.
- **`needs_review` is surfaced but still cannot be cleared.** The queue now shows every
  flagged item and the reason, and the flag still blocks rental (ADR-0003) — so
  releasing an item is a database edit. The screen says so rather than offering a
  button that would fail.
  **Why:** clearing needs a decision nobody has made — what evidence releases an item,
  and who records it. Inventing it to fill a screen is how an audit trail becomes
  decoration.
  **Future:** a clear-flag action with the decision recorded, due before the Phase 2
  gate.
- **Sign out is client-side only.** It drops the app's state and returns to the login
  screen; the cookie is not revoked server-side, because the session is a signed cookie
  with no server record and there is no logout route.
  **Why:** stateless sessions were the cheap correct thing for one process, and expiry
  and revocation were out of Phase 1's scope.
  **Future:** a logout route plus session expiry — pointed at `/security-review`.
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

- Rental engine — items have statuses but cannot be rented or returned. No `Rent`
  action exists, which is why the wireframe's is absent
- The AI layer — semantic search and the Inventory Auditor. The wireframe's "Ask AI…"
  bar is absent for the same reason
- Editing an item's name, brand or date — only status changes and deletion exist
- Field-level authorization — every signed-in employee sees `notes` and `history`,
  which are admin- and auditor-facing
- Logout, session expiry, login throttling
- CI, vitest, a health endpoint

### 🔮 Next Steps (24h Roadmap)

In order, one branch and one deployed version each — the phases in the table above:

1. **Clear a `needs_review` flag.** The one piece of Phase 1's own scope that shipped
   read-only, and ADR-0003 says it must not reach the Phase 2 gate unresolved.
   `/security-review` runs alongside it, against the three items waiting in
   [`BACKLOG.md`](BACKLOG.md).
2. **Phase 2 — rental engine.** Rent and return, with `Repair` and `needs_review`
   blocking through one guard (ADR-0003).
3. **Phase 3 — AI layer and hardening.** Semantic search and the Inventory Auditor,
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
| **Demo credentials are published on a public instance, on an admin account** | A reviewer signing in within ten seconds is worth more than credential hygiene on a throwaway instance, and ADR-0005 chose that openly rather than quietly. The deployment's own bootstrap admin is a separate account whose credential is not published. | A read-only demo role, or per-reviewer invite links. Anyone with this README can currently delete inventory. |
| **`notes` and `history` are visible to every signed-in employee** | The endpoint returns whole items, and ADR-0006 closed the public half of this — a stranger with the URL no longer sees them. Field-level authorization is a separate piece of work that Phase 1 did not do. | Role-aware serialisation, so auditor-facing free text reaches admins only. `/security-review` before the Phase 1 gate. |
| **Nothing can clear `needs_review`** | The queue is surfaced and read-only. Clearing needs a decision nobody has made — what evidence releases an item, and who records it — and inventing one to fill a screen is how an audit trail becomes decoration. | A clear-flag action with the decision recorded. ADR-0003 says this must not reach the Phase 2 gate. |
| **The frontend has no tests** | `brainstorm.md` §3 lists vitest in Phase 0. It was true then that the page was one fetch and a table; it is not true now — the UI has a roving-tabindex table, a `401`-to-login path and filter counts. This is the shortcut that aged worst. | vitest over the keyboard behaviour and the api client, which are logic rather than markup. |
| **`test_serves_built_bundle_at_root` needs `npm run build` first** | It asserts against the real `frontend/dist` on purpose — a fixture directory would prove the mount works, not that the built bundle is served. | CI builds the frontend before running pytest. |
| **No CI** | Time. The tests exist and run locally; automating them was the cut. | A workflow running both build steps and both suites. |
| **The app seeds itself on boot when the database is empty** | The deploy target offers no way to run a one-off command against the mounted volume: Railway's API has no exec or SSH, `preDeployCommand` silently did not run, and `railway ssh` needs an SSH key. Seeding at startup was the only mechanism left. An emptiness guard makes it safe — once rentals exist the table is never empty, so it can never wipe them. | A migration step or a one-off job. Boot logic should not write data. See [`BACKLOG.md`](BACKLOG.md). |
| **Deploying needed three human-in-the-loop steps** | Browser OAuth for the Railway MCP, a *second* browser authorization for the Railway CLI, and an SSH key — none of which any tooling removes. Seed-on-boot-if-empty was chosen partly to delete the manual seeding step for whoever redeploys next. | Nothing to fix in this codebase; recorded because the deploy story is otherwise easy to tell as smoother than it was. |
| **Sign out does not revoke the session** | The session is a signed cookie with no server-side record, which was the cheap correct thing for one process. There is no logout route, so the control clears the client and says so. | A logout route and session expiry. A leaked cookie is valid until `SECRET_KEY` changes. |

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
