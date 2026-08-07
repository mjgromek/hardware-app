# Hardware Hub

Internal tool for Booksy employees to manage, rent and maintain equipment.
Recruitment task, Early Careers Programme.

`CONTEXT.md` = domain language. `brainstorm.md` (v2) = phased plan.
`docs/adr/` = settled decisions. `BACKLOG.md` = non-blocking findings.

## Stack

FastAPI + SQLAlchemy + SQLite. Vue 3 + Vite. pytest + vitest. Railway.
**Single origin**: FastAPI serves the built `dist/`. One URL, no CORS. (ADR-0001)

## Working pace: read this first

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
- **No mutation testing** unless the code is load-bearing: guards, concurrency,
  transaction boundaries. Conventional CRUD gets written, run, moved on.
- **Three commits per phase:** one `test:` (red), one `feat:` (green), one
  `chore:` (deploy). Not per slice.
- **Don't re-verify what the suite proves.** Green is the report.

## Non-negotiables

- **TDD.** No production code before a failing test. Use `/tdd`.
- **Never patch files with `python str.replace` or `sed`.** Use the Edit tool, which
  fails loudly when the target text does not match. Four silent no-op replaces in one
  session produced two features reported as built that did not exist, and two wrong
  theories reasoned on top of files that never changed. A build succeeding is not
  evidence that a change landed.
- **Every test that creates an entity gets a sibling that destroys it** and replays
  every consumer of its identity: sessions, rentals, audit actors, whatever names it.
  The class this suite was missing was not security, it was entity lifecycle: a
  recycled rowid produced full admin takeover under 91 green tests (ADR-0013), and the
  same blindness resurfaced as a rent racing a deletion (`test_lifecycle_race`). When
  the destroy path can race a consumer, the write goes before the read.
- **Every schema change ships with a migration test.** Boot over the *previous*
  table shape built in raw SQL, then assert a real request succeeds, not that
  `create_app` returned. The suite builds every database from scratch, where
  `create_all` creates everything, so it is structurally blind to upgraded volumes.
  Two production defects have now come from exactly that blind spot.
- **Never commit to `main`.** Branch per phase, merge by PR after human review.
- **Conventional Commits.** Every commit updates `AI_LOG.md`: 3 lines, in the
  moment. Long-form only for genuine corrections; seven exist, indexed at the top of
  AI_LOG.md, and the bar for an eighth is a genuine process failure, not a bad day.
- **Secrets server-side only.** Nothing reaches the Vue bundle.
- **Status enum is exactly** `Available | In Use | Repair`. `"Unknown"` maps to
  `needs_review`. Nothing is silently deleted; bad rows go to
  `hardware_quarantine` with a reason. (ADR-0002)
- **`needs_review` blocks rental**, `409`, same guard as `Repair`. (ADR-0003)
- **At least one admin must always exist**, `409` guard. (ADR-0005)
- **No public read surface.** Every data route needs a session, `401` without.
  `GET /` stays open or nobody can log in. (ADR-0006)
- **Target 15–20 commits total.**

## Phases

```
P0  foundation, data audit, deploy v0     ✅ DONE, merged, tagged, live
P1  auth, admin, dashboard                ✅ DONE, merged, tagged v1-admin, live
P2  rental engine                         ✅ DONE, merged, tagged v2-rental, live
P3  AI layer + production hardening       ◐ green, deployed v3, at the gate
P4  UI fidelity to the wireframes         planned, starts only after P3 ships
    final polish, one commit on main
```

Each: branch → red → green → deploy → review gate → merge → tag.

## Deploy: the fast path

Railway, one service, SQLite on a persistent volume. Per phase:

1. `npm run build` in `frontend/`, because `test_serves_built_bundle_at_root` needs the
   real `dist/`
2. **Deploy with `railway up --detach`** (CLI at `/opt/homebrew/bin/railway`, already
   authenticated). The service's GitHub trigger now tracks `main`, fixed in the
   dashboard on 2026-08-07, so a push to `main` deploys and a variable change no
   longer resurrects an old build.
3. Seeding is automatic on boot **only when the table is empty**. Never run a
   seed command by hand, and never remove that guard (it's what stops a restart
   destroying rentals)
4. **Run the smoke check. A deploy is not done until it passes against the live
   URL**, not when `railway up` returns, not when the suite is green:

   ```
   SMOKE_URL=<live URL> SMOKE_EMAIL=admin@booksy.com SMOKE_PASSWORD=… \
     .venv/bin/python -m pytest tests/test_smoke_deployed.py -q
   ```

   It skips silently without `SMOKE_URL`, so it never runs in the ordinary suite.
   It is the only test that can fail while the code is correct, which is the
   point. All 152 local tests passed the whole time the live URL was serving a
   pre-auth v0 image (Correction #4, and again #6). Source-level green says
   nothing about what is deployed.
5. Add the URL to the README live-versions table

No SSH, no `preDeployCommand`: both were tried and neither works on this plan.

## Docs that must stay current

`AI_LOG.md` every commit · `docs/adr/` every architectural decision ·
`docs/PROMPT_TRAIL.md` after each grilling · `docs/WIREFRAME_JUSTIFICATION.md`
per UI deviation · `README.md` live-versions table and the four graded sections
(✅ Fully Implemented / ⚡ Shortcuts & Hacks / ⚠️ Partial / 🔮 Next Steps).

Shortcuts enter the README when taken, with a Why and a Future. A documented hack
beats a hidden one.
