# Hardware Hub

Internal tool for Booksy employees to manage, rent and maintain equipment.
Recruitment task, Early Careers Programme.

`CONTEXT.md` = domain language. `brainstorm.md` (v2) = phased plan.
`docs/adr/` = settled decisions. `BACKLOG.md` = non-blocking findings.

## Stack

FastAPI + SQLAlchemy + SQLite. Vue 3 + Vite. pytest + vitest. Railway.
**Single origin** — FastAPI serves the built `dist/`. One URL, no CORS. (ADR-0001)

## Working pace — read this first

Time is the binding constraint. Correctness that ships late loses to correctness
that ships.

- **Report in 5 lines or fewer.** What you did, what's green, what's next. Expand
  only when something is wrong.
- **Never restate work already described.** No recap tables, no summaries of the
  last message.
- **Make reversible decisions yourself.** Note them in one line and continue. Stop
  only for: security, data loss, or a contradiction with an ADR.
- **Non-blocking findings go to `BACKLOG.md`.** Do not ask. Only interrupt if
  something makes the current work wrong.
- **No mutation testing** unless the code is load-bearing — guards, concurrency,
  transaction boundaries. Conventional CRUD gets written, run, moved on.
- **Three commits per phase:** one `test:` (red), one `feat:` (green), one
  `chore:` (deploy). Not per slice.
- **Don't re-verify what the suite proves.** Green is the report.

## Non-negotiables

- **TDD.** No production code before a failing test. Use `/tdd`.
- **Every schema change ships with a migration test.** Boot over the *previous*
  table shape built in raw SQL, then assert a real request succeeds — not that
  `create_app` returned. The suite builds every database from scratch, where
  `create_all` creates everything, so it is structurally blind to upgraded volumes.
  Two production defects have now come from exactly that blind spot.
- **Never commit to `main`.** Branch per phase, merge by PR after human review.
- **Conventional Commits.** Every commit updates `AI_LOG.md` — 3 lines, in the
  moment. Long-form only for genuine corrections; 3–4 exist already, that's enough.
- **Secrets server-side only.** Nothing reaches the Vue bundle.
- **Status enum is exactly** `Available | In Use | Repair`. `"Unknown"` maps to
  `needs_review`. Nothing is silently deleted — bad rows go to
  `hardware_quarantine` with a reason. (ADR-0002)
- **`needs_review` blocks rental**, `409`, same guard as `Repair`. (ADR-0003)
- **At least one admin must always exist**, `409` guard. (ADR-0005)
- **No public read surface.** Every data route needs a session, `401` without.
  `GET /` stays open or nobody can log in. (ADR-0006)
- **Target 15–20 commits total.**

## Phases

```
P0  foundation, data audit, deploy v0     ✅ DONE — merged, tagged, live
P1  auth, admin, dashboard                ✅ DONE — merged, tagged v1-admin, live
P2  rental engine                         ✅ DONE — merged, tagged v2-rental, live
P3  AI layer + production hardening       ◐ green, deployed v3, at the gate
P4  UI fidelity to the wireframes         planned — starts only after P3 ships
    final polish — one commit on main
```

Each: branch → red → green → deploy → review gate → merge → tag.

## Deploy — the fast path

Railway, one service, SQLite on a persistent volume. Per phase:

1. `npm run build` in `frontend/` — `test_serves_built_bundle_at_root` needs the
   real `dist/`
2. **Deploy with `railway up --detach`** (CLI at `/opt/homebrew/bin/railway`, already
   authenticated). Pushing the branch does NOT deploy: the service's GitHub trigger
   still tracks the Phase 0 branch, so a push deploys nothing — and **any variable
   change redeploys v0**, which has no auth and serves the volume's data publicly.
   This happened once (2026-08-07, AI_LOG Correction #5). Until the tracked branch is
   fixed in the dashboard (human-only), follow every variable change with an
   immediate `railway up`.
3. Seeding is automatic on boot **only when the table is empty** — never run a
   seed command by hand, and never remove that guard (it's what stops a restart
   destroying rentals)
4. Add the URL to the README live-versions table

No SSH, no `preDeployCommand` — both were tried and neither works on this plan.

## Docs that must stay current

`AI_LOG.md` every commit · `docs/adr/` every architectural decision ·
`docs/PROMPT_TRAIL.md` after each grilling · `docs/WIREFRAME_JUSTIFICATION.md`
per UI deviation · `README.md` live-versions table and the four graded sections
(✅ Fully Implemented / ⚡ Shortcuts & Hacks / ⚠️ Partial / 🔮 Next Steps).

Shortcuts enter the README when taken, with a Why and a Future. A documented hack
beats a hidden one.
