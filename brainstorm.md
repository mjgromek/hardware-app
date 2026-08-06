# Hardware Hub — Build Brainstorm

**Project:** Booksy Early Careers recruitment task — "AI-Native Hardware Hub"
**Method:** TDD, branch-per-MVP, human review gate between versions
**Stack:** Python (FastAPI) + SQLite backend, Vue 3 + Vite frontend
**Skills:** `/grill-me` · `/tdd` · `/improve-codebase-architecture` · `frontend-design`

---

## 0. Ground Rules

| Rule | In practice |
|---|---|
| **Tooling before code** | MCPs, plugins, `CLAUDE.md` and `CONTEXT.md` exist before the scaffold. §1. |
| **Grill before building** | Every MVP opens with `/grill-me`. It is user-invoked — it will never fire on its own. §2.1. |
| **Red → Green → Refactor** | `/tdd` drives every implementation. No production code before a failing test. §2.2. |
| **One branch per MVP** | `feat/mvp-N-name`, merged to `main` only after the review gate. §3. |
| **Human review gate** | You review and approve each version before the next branch opens. §4. |
| **Deploy every MVP** | Every version ends with a live public URL, recorded in the README. |
| **AI log every commit** | `AI_LOG.md` is touched in *every* commit. §5. |
| **15–25 commits** | ~3 per phase across six phases. Readable, not noise, not one dump. |
| **Honesty is a feature** | Shortcuts land in the README trade-offs table the moment they are taken. |

### Commit shape per phase (≈18–21 total)

1. `test(mvp-N): <failing specs>` — red, from the `/tdd` session, + AI log entry
2. `feat(mvp-N): <implementation>` — green, + AI log entry
3. `chore(mvp-N): deploy vN + docs` — live URL, README + ADR updates, tag

A 4th `fix(mvp-N):` commit only when a review gate genuinely demands it. Keeps the ceiling near 25 without padding.

---

## 1. Phase −1 — Tooling Setup

Do all of this before the repo has a single line of application code.

### 1.1 Connect MCP servers (blocking)

| MCP | Why on day zero |
|---|---|
| **GitHub** | Branches, commits, PRs, tags, Actions status inside the loop. The whole workflow in §3 leans on it. |
| **Railway** | `create-project`, `create-deployment`, `get-logs`, `get-status`. Needed at Phase 0 because v0 deploys immediately. |
| **Figma** | Only if the wireframes are a Figma file — `get_design_context` beats working from screenshots, and feeds `frontend-design` real constraints. |

Opportunistic: **Playwright** (E2E at review gates), **Context7** (current FastAPI/Vue docs, cuts hallucinated APIs), **Sentry**, **SQLite**.

### 1.2 Install the skills

```bash
/plugin install mattpocock-skills                      # grill-me, tdd, improve-codebase-architecture
/plugin install frontend-design@claude-plugins-official
/plugin                                                # confirm both enabled
```

Both live in the official marketplace — nothing to add first.

### 1.3 Run the setup command (once per repo)

```bash
/setup-matt-pocock-skills
```

Not optional — the engineering skills read its config. It asks three things:

- **Issue tracker** → answer **local files**. A GitHub Projects board is overkill for a 5-hour task and adds noise to the repo.
- **Triage labels** → defaults are fine, `/triage` is not in this plan.
- **Docs location** → `docs/`.

### 1.4 Write the doc scaffolding

See §6 for the full map. At minimum, before any code: `CLAUDE.md`, `CONTEXT.md`, empty `AI_LOG.md`, `docs/adr/`.

**Commit 1 of the project** is this setup — plugin config, `CLAUDE.md`, `CONTEXT.md`. Log in `AI_LOG.md` which MCPs and skills you connected and in what order.

---

## 2. How the Four Skills Are Used

The single most important fact: **`/grill-me` and `/improve-codebase-architecture` are user-invoked.** They fire only when you type them. `/tdd` and `frontend-design` are model-invoked and will engage on their own. The two that need deliberate triggering are the two that add the most value — build the habit or lose them.

### 2.1 `/grill-me` — before every branch

Relentless interview, one question at a time, until every branch of the decision tree is resolved. Aimed at plans and designs, not code.

**Run it at the start of every MVP, before the branch exists.** The output is the spec you then hand to `/tdd`. Where it earns its keep in this project:

| Phase | What the grilling has to force out |
|---|---|
| 0 | Quarantine vs. delete vs. repair for each dirty record. What does `needs_review` mean in the UI? |
| 1 | Session strategy — JWT or cookie? Where do admin routes get guarded, middleware or per-endpoint? What happens when the last admin deletes themselves? |
| 2 | Concurrency. Can a user hold two items? Does an admin flipping to Repair kill an active rental? Who may return an item — renter, admin, both? |
| 3 | What "semantic search" means precisely. Failure behaviour when the LLM is down. What the auditor may and may not assert. |
| 4 | What must be true before a URL counts as production. Reset/reseed story. |
| 5 | What ships and what is honestly declared missing. |

Every grilling session produces an ADR in `docs/adr/` for any decision worth defending in the interview. Paste the transcript into `docs/PROMPT_TRAIL.md` — it is your prompt-trail deliverable, for free.

> **Note:** `/grill-me` is the non-code variant. Its sibling `/grill-with-docs` does the same interrogation *and* maintains `CONTEXT.md` + ADRs inline. If you want the domain glossary maintained automatically rather than by hand, that is the better tool. Sticking with `/grill-me` as chosen means you write ADRs yourself — cheap, but do not skip it.

### 2.2 `/tdd` — the implementation engine

Red-green-refactor, one vertical slice at a time. It will not write implementation before a failing test exists, and it carries opinions on what makes a bad test (testing implementation instead of behaviour, over-mocking, assertions that cannot fail).

**How to drive it:** hand it the grilled spec plus the test list from the MVP section below. Those lists are *inputs*, not outputs — you already know the critical behaviours, so do not make the agent guess them.

**Slice discipline:** each vertical slice = one route/behaviour end to end. "Admin can toggle Repair" is a slice. "The admin panel" is not — it will produce shallow tests and a wide diff.

`/tdd` is model-invoked, so it may engage automatically. Type `/tdd` explicitly anyway at the start of each implementation session so the loop is unambiguous.

### 2.3 `/improve-codebase-architecture` — at the review gates

Scans for deepening opportunities — Ousterhout's deep modules, a lot of behaviour behind a small interface — renders a visual HTML report, then grills you through whichever one you pick.

**It needs a codebase to exist.** Running it at Phase 0 or MVP 1 wastes a session on ~200 lines. Schedule:

| When | Expect it to surface |
|---|---|
| After MVP 2 | Rental transition logic leaking out of the state machine into route handlers. This is *the* refactor of the project — the state machine must be one deep module or MVP 3 gets built on sand. |
| After MVP 3 | The LLM layer entangled with query logic; the prompt/parse/validate boundary wanting to be one interface. |
| During MVP 5 | Final sweep. Take the cheap wins, log the rest as ⚠️ Partial with reasoning. |

Each accepted refactor becomes a `refactor(mvp-N):` commit — and the report itself is superb interview material: *"I ran an architecture scan after the rental engine, it flagged X, here is what I changed and why."*

**Discipline:** it will find more than you have time for. Take one or two per run and log the rest in the README's 24h Roadmap. Do not let it derail a phase.

### 2.4 `frontend-design` — MVP 1 and MVP 5

Model-invoked, activates when you ask for UI. Forces a declared aesthetic — purpose, tone, constraints, differentiation — before a single CSS rule.

**The tension you must manage:** this skill's bias is bold and distinctive. The brief supplies wireframes and asks for justified deviations. Left unconstrained it will produce something that looks nothing like what Booksy asked for, with no explanation attached.

**Constrain it explicitly at MVP 1** — feed it, in the same prompt:

- the wireframes (via Figma MCP, or the screenshots)
- "internal tool, Booksy employees, dense data table is the primary surface"
- "clarity and scannability over expressiveness; status must be legible at a glance"
- accessibility: focus states, keyboard nav, contrast

Then let it make one or two deliberate, defensible deviations. Every deviation goes in `docs/WIREFRAME_JUSTIFICATION.md` **as it is made**, not reconstructed in MVP 5. A justified deviation scores higher than a traced wireframe — an unjustified one scores lower than either.

### 2.5 What you lose without superpowers

Matt's set has no worktree or branch machinery. `/implement` drives `/tdd`, but branch management is manual. §3 does it with plain git — simple enough, but nothing automates it. If you later want the worktree workflow back, superpowers can be installed alongside; just be deliberate about which skill owns the TDD loop, because both have one.

---

## 3. Multi-Branch Workflow

`main` stays green and deployable at all times. Each MVP lives on its own branch, in its own worktree.

```
main ──●───────●───────●───────●───────●───────●
       │v0     │v1     │v2     │v3     │v4     │v5
       ▲       ▲       ▲       ▲       ▲       ▲
  chore/mvp-0  feat/   feat/   feat/   chore/  polish/
  foundation   mvp-1-  mvp-2-  mvp-3-  mvp-4-  mvp-5-
               admin   rental  ai      deploy  final

  each ▲ = merge, ONLY after your review gate passes
```

### The loop, per MVP

1. **Grill.** `/grill-me` on the MVP section below. Output: a spec + any ADRs. On `main`, before the branch.
2. **Branch + worktree.** `git worktree add ../hub-mvp-N feat/mvp-N-name`. Your main checkout stays usable.
3. **Red.** `/tdd` with the spec and test list. Failing tests. → commit 1
4. **Green.** Implement until the suite passes. → commit 2
5. **Architecture pass.** `/improve-codebase-architecture` (MVP 2 onward). → optional `refactor:` commit
6. **Deploy + document.** Live vN, README, tag. → commit 3
7. **Review gate.** Open a PR. **Stop. Hand to you.** §4
8. **Merge**, remove the worktree, open the next branch.

**Why it matters beyond hygiene:** the PR diff *is* the review artifact — no separate write-up. A failed review is a fix commit on the branch, not a revert on `main`. And reviewers read the history as six self-contained units of work.

**Never commit directly to `main`.** Merges only, via PR.

---

## 4. The Review Gate

An MVP is not finished when tests pass. It is finished when *you* have reviewed it and said go.

### Automated — must pass to open the gate

```
[ ] Full test suite green (unit + integration)
[ ] Lint / typecheck clean
[ ] CI green on the branch
[ ] vN deployed and reachable at a public URL
```

### Yours — the actual gate

```
[ ] Read the PR diff end to end. Anything you cannot explain does not merge.
[ ] Click through the live vN URL. Does it behave as intended?
[ ] Do the tests test behaviour, or do they test the implementation?
[ ] Ran /improve-codebase-architecture (MVP 2+)? Report reviewed, actions decided?
[ ] AI_LOG.md entries read as honest and specific, not retrofitted.
[ ] Any shortcut taken is already in the README trade-offs table.
[ ] Any UI deviation is already in docs/WIREFRAME_JUSTIFICATION.md.
```

**Outcomes:** ✅ Approve → merge, tag, next branch · 🔄 Changes → fix commit on the same branch, re-gate · ⛔ Reject → shrink scope, do not carry debt forward.

The next branch is not created until the gate closes. That constraint is the whole point: it stops unreviewed AI output from compounding.

---

## 5. The AI Log — Continuous and Frequent

Required deliverable, and the one most candidates fake at the end. Reviewers can tell.

- **Every commit touches `AI_LOG.md`.** No entry, not done.
- **Write in the moment** — not at phase end, definitely not at project end.
- **Append-only**, timestamped, cross-referenced to commit SHAs.
- **Log the failures.** A log with no wrong answers in it is not believable.

### Entry format

```markdown
## [MVP 2 · commit 2] Rental guard rejected broken hardware — but not concurrently

**Prompt:** "/tdd — implement rent() against the grilled spec, slice 3"
**Tools:** Claude Code + /tdd (mattpocock-skills), Railway MCP for the deploy check
**What the AI produced:** A check-then-write with no transaction boundary.
**What was wrong:** Two concurrent rents both pass the availability check
  → double-booking. Classic TOCTOU.
**How I caught it:** /grill-me forced the concurrency question during planning,
  so `test_concurrent_rent_only_one_succeeds` existed first and failed.
**The correction:** Guided it to a conditional UPDATE
  (`UPDATE ... WHERE status='Available'`) asserting rowcount == 1.
**Commit:** `feat(mvp-2): atomic rent/return state machine (a1b2c3d)`
```

Note how the grilling session shows up in the log. Documenting the *process* that caught the bug is worth more than documenting the bug.

### Coverage by submission

1. **Tooling** — Claude Code, the four skills, every MCP connected
2. **Data strategy** — link to `docs/DATA_AUDIT.md`; what the AI spotted vs. what you spotted
3. **Prompt trail** — `docs/PROMPT_TRAIL.md`, largely the grilling transcripts
4. **The "Correction"** — at least one real case where the AI was wrong. Do not invent it. The concurrency bug, over-permissive CORS, or an API key leaked into the Vue bundle are the ones that actually happen.

---

## 6. Repo Documentation Map

| File | Written by | Purpose |
|---|---|---|
| `CLAUDE.md` | You, Phase −1 | **The constitution.** Read every session. Stack, TDD rule, commit format, never-commit-to-main, AI-log-every-commit. Skills are opportunistic; this is not. |
| `CONTEXT.md` | You + agent | Shared language. "Quarantine record", "semantic contradiction", "orphan rental", "deepening". Keeps the agent concise and names things consistently. |
| `docs/adr/NNNN-*.md` | Agent, during grilling | One per defensible decision. Quarantine over deletion; structured extraction over RAG; Railway over Vercel. **Direct evidence for "engineering decisions are expensive."** |
| `AI_LOG.md` | You, every commit | Required deliverable. §5. |
| `docs/DATA_AUDIT.md` | Phase 0 | Seed defects + how each was handled. |
| `docs/PROMPT_TRAIL.md` | Accumulated | Grilling transcripts + architecture-shaping prompts. |
| `docs/WIREFRAME_JUSTIFICATION.md` | MVP 1 onward | Where you followed the wireframes, where you deviated, why. Explicitly requested by the brief. |
| `README.md` | Continuous | Setup, live-versions table, ✅/⚡/⚠️/🔮 status summary. |

### `CLAUDE.md` starter

```markdown
# Hardware Hub

Internal tool for managing, renting and maintaining company equipment.
Booksy Early Careers recruitment task. See CONTEXT.md for domain language.

## Stack
- Backend: Python, FastAPI, SQLAlchemy, SQLite (file-based, portability is deliberate)
- Frontend: Vue 3, Vite
- Tests: pytest (backend), vitest (frontend)

## Non-negotiables
- TDD. No production code before a failing test. Use /tdd.
- Never commit to main. Branch per MVP, merge via PR after human review.
- Conventional Commits: test: / feat: / fix: / refactor: / chore: / docs:
- Every commit updates AI_LOG.md. No entry, not done.
- Secrets are server-side only. No API key ever reaches the Vue bundle.
- Hardware status enum is exactly: Available | In Use | Repair.
  "Unknown" is not a status — it is a needs_review flag.

## Before starting any MVP
Run /grill-me on the MVP section of brainstorm.md. Capture decisions as ADRs
in docs/adr/. No implementation until the spec is settled.
```

---

## 7. Phase 0 — Foundation & Data Audit

Branch: `chore/mvp-0-foundation` · Skills: `/grill-me` → `/tdd`

> The dataset gets audited **before any feature code exists**. The seed is deliberately dirty, and handling it is explicitly graded ("your ability to audit AI-generated data migrations").

### 7.1 Seed defects found

11 records, ids 1,2,3,4,5,6,7,**4**,9,10,11 → only 10 unique ids.

| # | Record | Defect | Class |
|---|---|---|---|
| 1 | id `4` twice (Galaxy S21 + "Duplicate ID Test Laptop") | Primary-key collision | **Structural — blocks import** |
| 2 | id `8` missing | Sequence gap | Cosmetic |
| 3 | id `6` MX Master 3 — `purchaseDate: 2027-10-10` | Purchase date in the future | Validation |
| 4 | id `9` iPad Pro — `"22-05-2023"` | DD-MM-YYYY vs ISO everywhere else | Format |
| 5 | id `9` — `brand: "Appel"` | Typo / brand not normalised | Data quality |
| 6 | id `10` — `brand: ""`, `purchaseDate: null`, `status: "Unknown"` | Empty + null + status outside the enum | Validation |
| 7 | id `5` Dell XPS — `Available` but `notes: "Battery swelling, do not issue without service."` | Status contradicts notes | **Semantic — safety risk** |
| 8 | id `11` MacBook Air — `Available` but `history: "liquid damage"` | Same contradiction | **Semantic** |
| 9 | id `2` `In Use` with no `assignedTo`; id `7` `In Use` with one | Orphan rental / inconsistent shape | Referential integrity |
| 10 | `notes`/`assignedTo`/`history` on some records only | Non-uniform schema | Schema |

### 7.2 Decisions to grill and encode

- **Enum:** `Available | In Use | Repair`. `Unknown` maps to a `needs_review` flag — nothing is silently deleted.
- **Quarantine-based ingestion, not lossy.** Clean rows to `hardware`, rejected/repaired rows to `hardware_quarantine` with a `reason`. Nothing dropped. The most defensible choice in the project → **ADR-0001**.
- **Duplicate id 4** → second record re-keyed to 12, original kept as `source_id`, logged.
- **Semantic contradictions (5, 11) stay in the DB deliberately** — they are the demo material for the MVP 3 auditor. → **ADR-0002**.

### 7.3 Deliverables

- Scaffold, `pyproject.toml` / `package.json`, `.env.example`, `.gitignore`
- pytest + vitest wired, one trivial passing test each
- `scripts/seed.py` + `docs/DATA_AUDIT.md`
- CI: GitHub Actions on push
- **Deploy v0** — skeleton live, proving the pipeline before there is anything to lose

### Tests first

```
test_seed_rejects_duplicate_id
test_seed_normalises_date_formats
test_seed_quarantines_unknown_status
test_seed_flags_future_purchase_date
```

**→ Review gate → merge → tag `v0-foundation`**

---

## 8. MVP 1 — Admin Command Center

Branch: `feat/mvp-1-admin` · Skills: `/grill-me` → `/tdd` → `frontend-design`

**Goal:** An admin logs in, manages the hardware catalogue, and creates the user accounts that are the only way into the system.

### Scope

- Auth: login screen, session/JWT, `admin` vs `user` role. **No self-registration.**
- Admin: add hardware, delete hardware, toggle Repair
- Admin: create user accounts
- Smart Dashboard: Name / Brand / Purchase Date / Status, sortable and filterable
- `needs_review` quarantine queue surfaced in the admin view — turns Phase 0 into visible product

### Frontend

First `frontend-design` session. Constrain it per §2.4: wireframes in, internal-tool framing, clarity over expressiveness, accessibility from the start. Start `docs/WIREFRAME_JUSTIFICATION.md` in this phase — do not defer it.

### Tests first

```
test_login_rejects_unknown_user
test_login_rejects_wrong_password
test_non_admin_cannot_create_user          # authorization, not just authentication
test_non_admin_cannot_delete_hardware
test_admin_can_toggle_repair_status
test_dashboard_sorts_by_purchase_date
test_dashboard_filters_by_status
test_password_is_hashed_not_stored_plaintext
```

**→ Deploy v1 → Review gate → merge → tag `v1-admin`**

---

## 9. MVP 2 — The Rental Engine

Branch: `feat/mvp-2-rental` · Skills: `/grill-me` → `/tdd` → `/improve-codebase-architecture`

**Goal:** Rent and return, with guards that make impossible states unreachable.

### Scope

- Rent (`Available → In Use`, records `assignedTo`), Return (`In Use → Available`)
- State machine as single source of truth — transitions in one place, not scattered across endpoints
- Rental history table — build now, MVP 3 feeds on it
- Backfill: id 2 is `In Use` with no assignee → resolved as an orphan rental at seed time

### Legal transitions

```
Available ──rent──▶ In Use ──return──▶ Available
    │                                      │
    └──────── admin toggle ───▶ Repair ◀───┘
```

Anything off this diagram → `409 Conflict` with a readable reason.

### Tests first

```
test_cannot_rent_hardware_in_repair          # ← the example from the brief
test_cannot_rent_hardware_already_in_use
test_cannot_return_hardware_not_rented
test_cannot_return_someone_elses_rental
test_rent_then_return_restores_available
test_concurrent_rent_only_one_succeeds       # atomic conditional UPDATE
test_rental_history_records_both_ends
```

> The brief asks for "at least 3 critical tests." Seven sharp ones — including the concurrency case nobody writes — is a cheap way to stand out.

### First architecture pass

Run `/improve-codebase-architecture` before the gate. Expect transition logic leaking into route handlers. Fix it here — the state machine must be one deep module or MVP 3 gets built on sand. → **ADR** for the resulting boundary.

**→ Deploy v2 → Review gate → merge → tag `v2-rental`**

---

## 10. MVP 3 — The AI-Native Layer

Branch: `feat/mvp-3-ai` · Skills: `/grill-me` → `/tdd` → `/improve-codebase-architecture`

**Goal:** The "native" part. Ship **two** of the three options — semantic search is the demo, the auditor is the punchline.

### 10.1 Semantic Search (primary)

Natural language → filtered inventory. "Something to test a mobile app on" → iPhone 13 Pro Max, Galaxy S21, iPad Pro.

**Structured extraction, not RAG.** With ~12 records, embeddings are theatre. Have the LLM emit a *structured filter object* (categories, brands, status, keywords) validated against a Pydantic schema, then query SQLite with it. Faster, cheaper, fully testable, degrades gracefully. → **ADR**, and exactly the "engineering decisions are expensive" point the brief is fishing for.

### 10.2 Inventory Auditor (the payoff)

Runs over the catalogue including `notes` / `history` / quarantine and flags:

- Dell XPS 15 — **Available**, notes say battery swelling → *"Do not issue. Status contradicts service notes."*
- MacBook Air M2 — **Available**, history says liquid damage → *"Return inspection likely incomplete."*
- MX Master 3 — purchase date in the future
- id 10 — unidentifiable device, needs physical audit

Closes the loop with Phase 0: the AI finds the dirt you deliberately preserved instead of hiding. Most demo-able moment in the app.

### Guardrails

- LLM key server-side only, never in the Vue bundle — classic AI-generated mistake; if it happens it goes in the AI log
- Timeout + fallback to keyword search on API failure
- Response cached per query string

### Tests first

```
test_semantic_query_maps_to_filter_schema     # mocked LLM, deterministic
test_semantic_search_falls_back_on_api_error
test_semantic_search_never_returns_repair_items
test_auditor_flags_status_notes_contradiction
test_llm_key_absent_from_frontend_bundle
```

All LLM calls mocked in CI; one optional live integration test behind a marker.

### Second architecture pass

`/improve-codebase-architecture` before the gate. Expect the prompt/parse/validate boundary wanting to become one interface, and LLM concerns entangled with query logic.

**→ Deploy v3 → Review gate → merge → tag `v3-ai`**

---

## 11. MVP 4 — Production Deployment

Branch: `chore/mvp-4-deploy` · Skills: `/grill-me` → `/tdd`

Deploys have happened since v0; this phase makes the URL production-grade rather than "it loads".

**Railway recommended** — FastAPI plus a persistent volume for SQLite in one place, single repo, no serverless-filesystem problem. Vercel is the wrong shape: ephemeral filesystem, so SQLite resets on every cold start. Prefer Vercel anyway? Split frontend to Vercel, API to Fly.io/Render — and justify it. → **ADR**.

### Scope

- Secrets via platform env vars, `.env` never committed (verify: `git log -S "sk-"` returns nothing)
- Persistent volume for SQLite + documented reset/reseed command
- CORS locked to the deployed frontend origin
- Demo credentials in the README so a reviewer logs in within 10 seconds — matters more than it sounds
- Health endpoint + smoke test against the *deployed* URL, not localhost
- README "Live versions" table for v0–v4

### Tests first

```
test_health_endpoint_returns_ok
test_cors_rejects_unknown_origin
test_prod_config_requires_secret_key        # refuses to boot with a default secret
smoke_deployed_login_and_rent_flow          # runs against the live URL
```

**→ Deploy v4 → Review gate → merge → tag `v4-deploy`**

---

## 12. MVP 5 — Final Refinement

Branch: `polish/mvp-5-final` · Skills: `/improve-codebase-architecture` → `frontend-design` → `/grill-me`

Not new features. The pass that turns a working app into a submission.

### Scope

- **Final architecture sweep** — `/improve-codebase-architecture` one last time. Take the cheap wins; log the rest as ⚠️ Partial with reasoning. Do not start a refactor you cannot finish.
- **Frontend polish** — second `frontend-design` pass: empty states, loading states, error toasts, favicon, focus states, keyboard nav on the dashboard. Cheap; disproportionate impact on perceived quality.
- **README completion** — setup, architecture diagram, and the required status summary:
  - ✅ Fully Implemented
  - ⚡ Shortcuts & Hacks (each with Why + Future) — e.g. *"SQLite on a single volume; would be Postgres + connection pooling in production"*
  - ⚠️ Partial / Missing
  - 🔮 24h Roadmap (top 3) — largely pre-written by the architecture reports
- **`AI_LOG.md` final read-through** — ~90% written already from continuous journaling; this is editing, not authoring
- **`docs/PROMPT_TRAIL.md`** — grilling transcripts + architecture-shaping prompts
- **`docs/WIREFRAME_JUSTIFICATION.md`** — finalise; it has been accumulating since MVP 1
- **Commit history review** — `git log --oneline --graph` should read like a story
- **Interview prep** — `/grill-me` on your own submission. Being interrogated about your trade-offs by the agent before Booksy does it is the highest-leverage 20 minutes available to you.

### Final gate

```
[ ] Full suite green (unit + integration + deployed smoke)
[ ] Fresh-clone test: clone → follow README → app runs. No undocumented steps.
[ ] Reviewer test: someone else logs into the live URL with README credentials
[ ] git log reads as a clean incremental narrative, 15–25 commits
[ ] AI_LOG.md has an entry for every commit
[ ] Every ADR in docs/adr/ is one you can defend out loud
```

**→ Deploy v5 → Final review → merge → tag `v5-final`**

---

## 13. Scope Control

If the build runs long, cut in this order — and record every cut in the README's ⚠️ Partial/Missing section, which is itself worth points:

1. Second `frontend-design` polish pass (MVP 5)
2. Inventory Auditor reduced to a stub (10.2) — keep semantic search
3. Sentry / optional MCPs
4. CI pipeline — keep the tests, drop the automation
5. Architecture pass at MVP 3 — keep the one at MVP 2, it is load-bearing

**Never cut:** the tests, the AI log, the review gates, or the `/grill-me` session before each MVP. Grilling *saves* time — it prevents the rewrite you would otherwise discover mid-implementation.

---

## 14. Open Items

- **Wireframe screenshots not yet received.** They feed MVP 1 (`frontend-design` constraints) and `docs/WIREFRAME_JUSTIFICATION.md`. If they live in Figma, connect the Figma MCP in §1.1 rather than working from images.
- **LLM provider** — Gemini Flash (cheapest, generous free tier), Claude Haiku, or GPT-4o-mini. Decide before MVP 3, log the reasoning.
- **Repo visibility** — must be public at submission. Create it public from commit one to avoid a "made public" event at the end of the history.
- **`/grill-with-docs` vs `/grill-me`** — the former also maintains `CONTEXT.md` and ADRs inline. Worth reconsidering if hand-writing ADRs starts slipping.
