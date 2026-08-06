# Hardware Hub

Internal tool for Booksy employees to manage, rent and maintain company equipment.
Built as a recruitment task for the Early Careers Programme.

See `CONTEXT.md` for domain language. See `brainstorm.md` for the phased plan.
See `PROJECT_SPEC.md` for architecture once it exists.

## Stack

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite (file-based — portability is deliberate)
- **Frontend:** Vue 3, Vite
- **Tests:** pytest (backend), vitest (frontend)
- **Deploy:** Railway (persistent volume; Vercel's ephemeral filesystem would reset SQLite)

## Non-negotiables

- **TDD.** No production code before a failing test exists. Use `/tdd`.
- **Never commit to `main`.** Branch per MVP, merge via PR after human review.
- **Conventional Commits:** `test:` `feat:` `fix:` `refactor:` `chore:` `docs:`
- **Every commit updates `AI_LOG.md`.** No entry, not done. Write it in the moment,
  never reconstructed at the end.
- **Secrets are server-side only.** No API key ever reaches the Vue bundle.
- **Status enum is exactly** `Available | In Use | Repair`. `"Unknown"` is not a
  status — it maps to a `needs_review` flag. Nothing from the seed is ever silently
  deleted; bad rows go to `hardware_quarantine` with a reason.
- **Target 15–25 commits total.** Roughly three per phase. Meaningful, not noise,
  and never one giant dump.

## Workflow — every MVP

```
0. /grill-me                  YOU, main thread. Never delegated to an agent.
1. /to-spec                   → docs/specs/mvp-N.md
2. test-author (agent)        → failing tests. Writes tests/ ONLY, never src/
3. /implement (drives /tdd)   → green. Never edits tests/
4. architecture-scout (agent) → ranked report; YOU decide what to act on
5. mvp-reviewer (agent)       → docs/reviews/REVIEW_mvp-N.md
6. HUMAN GATE                 → you approve, merge, tag vN
```

Every handoff is a **file**. Agents share no memory — an undocumented handoff is
a dropped handoff.

Authorship and verification never share a context. That is the whole point of the
agent split: `test-author` cannot write `src/`, the implementer cannot edit
`tests/`, and `architecture-scout` and `mvp-reviewer` have no write access at all.

## Before starting any MVP

Run `/grill-me` on the relevant section of `brainstorm.md`. Capture every decision
worth defending as an ADR in `docs/adr/`. No implementation until the spec settles.

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
