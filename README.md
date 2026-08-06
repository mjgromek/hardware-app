# Hardware Hub

Internal tool for Booksy employees to manage, rent and maintain company equipment.
Built as a recruitment task for the Early Careers Programme.

**Stack:** FastAPI · SQLite · Vue 3 + Vite · deployed on Railway
**Method:** TDD, branch per phase, human review gate between versions

---

## Live versions

| Version | Phase | URL | Status |
| --- | --- | --- | --- |
| **v0** | Phase 0 — foundation, data audit, first deploy | https://hardware-hub-production-24b7.up.railway.app | ✅ live |
| v1 | Phase 1 — auth, admin, dashboard | — | 🔮 planned |
| v2 | Phase 2 — rental engine | — | 🔮 planned |
| v3 | Phase 3 — AI layer + hardening | — | 🔮 planned |

---

## Status

**✅ Done**

- Seed ingestion: structural validation, quarantine with reasons, nothing deleted
- SQLite persistence with caller-owned transactions and replace-semantics reseed
- `GET /api/hardware` — the full inventory
- Vue page listing every item with its status and review flag
- Single origin: one service, one URL, no CORS (ADR-0001)
- 28 tests, all green

**⚡ Partial**

- Frontend is one unstyled page. No router, no state management — Phase 1's job.
- `needs_review` is set and displayed but nothing can clear it yet (see trade-offs).

**⚠️ Missing**

- Authentication and roles — no login exists, so the API is fully public
- Rental engine — items have statuses but cannot be rented or returned
- The AI layer — semantic search and the Inventory Auditor
- CI, vitest, a health endpoint

**🔮 Planned** — Phases 1–3 above.

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
| **The API is entirely public** | Phase 0 exists to prove the pipeline end to end. Auth is Phase 1's whole subject, and stubbing it here would have meant building it twice. | Phase 1 adds session-cookie auth and role guards. |
| **`notes` and `history` are exposed by `/api/hardware`** | They are the free text the auditor reads, and the endpoint returns whole items. | Phase 1's roles decide who sees them. |
| **Nothing can clear `needs_review`** | The flag blocks rental (ADR-0003); the clearing UI is admin work, which is Phase 1. Until then a flagged item requires a database edit to release. | Phase 1 surfaces the queue with a clear-flag action. |
| **The frontend has no tests** | `brainstorm.md` §3 lists vitest in Phase 0. The page is one fetch and a table; a test would assert little. | vitest arrives when the frontend grows logic. |
| **`test_serves_built_bundle_at_root` needs `npm run build` first** | It asserts against the real `frontend/dist` on purpose — a fixture directory would prove the mount works, not that the built bundle is served. | CI builds the frontend before running pytest. |
| **No CI** | Time. The tests exist and run locally; automating them was the cut. | A workflow running both build steps and both suites. |
| **The app seeds itself on boot when the database is empty** | The deploy target offers no way to run a one-off command against the mounted volume: Railway's API has no exec or SSH, `preDeployCommand` silently did not run, and `railway ssh` needs an SSH key. Seeding at startup was the only mechanism left. An emptiness guard makes it safe — once rentals exist the table is never empty, so it can never wipe them. | A migration step or a one-off job. Boot logic should not write data. See [`BACKLOG.md`](BACKLOG.md). |
| **Deploying needed three human-in-the-loop steps** | Browser OAuth for the Railway MCP, a *second* browser authorization for the Railway CLI, and an SSH key — none of which any tooling removes. Seed-on-boot-if-empty was chosen partly to delete the manual seeding step for whoever redeploys next. | Nothing to fix in this codebase; recorded because the deploy story is otherwise easy to tell as smoother than it was. |
| **Admin bootstrap validated but unused** | `ADMIN_PASSWORD` is required in production and nothing consumes it yet — there is no users table until Phase 1. | Phase 1's seed creates admin #1 from it. |

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
| [`AI_LOG.md`](AI_LOG.md) | Every commit, and the corrections where the AI was wrong. |
| [`BACKLOG.md`](BACKLOG.md) | Findings deferred rather than acted on. |
| [`docs/PROMPT_TRAIL.md`](docs/PROMPT_TRAIL.md) | The grilling sessions that settled the plan. |
