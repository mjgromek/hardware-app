# Hardware Hub

Internal tool for Booksy employees to manage, rent and maintain company equipment.
Built as a recruitment task for the Early Careers Programme.

See `CONTEXT.md` for domain language. See `brainstorm.md` (v2) for the phased plan.
See `docs/adr/` for settled decisions. See `PROJECT_SPEC.md` for architecture once
it exists.

## Stack

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite (file-based — portability is deliberate)
- **Frontend:** Vue 3, Vite
- **Single origin:** FastAPI serves the built Vue `dist/` as static files. One
  service, one URL. **No CORS.** (ADR-0001)
- **Tests:** pytest (backend), vitest (frontend)
- **Deploy:** Railway (persistent volume; Vercel's ephemeral filesystem would reset SQLite)

## Non-negotiables

- **TDD.** No production code before a failing test exists. Use `/tdd`.
- **Never commit to `main`.** Branch per phase, merge via PR after human review.
  Exception: pre-Phase-0 setup commits.
- **Conventional Commits:** `test:` `feat:` `fix:` `refactor:` `chore:` `docs:`
- **Every commit updates `AI_LOG.md`.** No entry, not done. Write it in the moment.
- **Secrets are server-side only.** No API key ever reaches the Vue bundle.
- **Status enum is exactly** `Available | In Use | Repair`. `"Unknown"` is not a
  status — it maps to `needs_review`. Nothing from the seed is silently deleted;
  bad rows go to `hardware_quarantine` with a reason.
- **`needs_review` blocks rental.** Flagged items return `409` through the same
  guard as `Repair`. A flag that changes nothing is decoration. (ADR-0003)
- **At least one admin must always exist.** Enforced as a guard returning `409`,
  in the same layer as the rental guards. (ADR-0005)
- **Ingestion validates structure only.** Semantic judgement is the auditor's job,
  by declared design. (ADR-0002)
- **Target 15–20 commits**, roughly four per phase. Meaningful, not noise.

## Workflow — four phases

```
Phase 0  foundation, data audit, first deploy   settled by grilling 1
Phase 1  auth, admin, dashboard                 settled by grilling 1
Phase 2  rental engine                          /grill-me first
Phase 3  AI layer + production hardening        /grill-me first
final    one polish commit on main — not a phase
```

Each phase: branch → red → green → deploy vN → review gate → merge → tag.

Only Phases 2 and 3 get their own grilling. Phases 0 and 1 were settled by the
whole-project session — see `docs/PROMPT_TRAIL.md`.

## AI log — two formats

**Routine commits, three lines:**

```markdown
## [P1 · c2] Admin CRUD + role guards
/tdd against the phase-1 spec. Clean run, no corrections needed.
Commit: feat(phase-1): admin hardware and account management (a1b2c3d)
```

**Corrections, long form and rare.** What the AI produced, why it was wrong, how
you caught it, how you corrected it. **Three or four across the whole build** —
twenty uniform long entries is itself the texture that reads as batch-written.

## Documentation that must stay current

| File | When |
|---|---|
| `AI_LOG.md` | Every commit |
| `docs/adr/` | Every architectural decision |
| `docs/DATA_AUDIT.md` | Phase 0 |
| `docs/PROMPT_TRAIL.md` | After every grilling session |
| `docs/WIREFRAME_JUSTIFICATION.md` | Every UI deviation, as it is made |
| `README.md` | Live-versions table + ✅/⚡/⚠️/🔮 status summary |

## Honesty is a feature

Shortcuts go in the README trade-offs table **the moment they are taken**, each with
the Why and the Future refactor. A documented hack scores better than a hidden one.
