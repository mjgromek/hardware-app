# AI Development Log

Append-only. Newest entries at the bottom. **Every commit gets an entry**, written
at the time — not reconstructed at the end.

Failures and wrong turns stay in. A log with no wrong answers in it did not happen.

---

## Tooling

| Layer | Choice |
|---|---|
| Agent | Claude Code |
| Skills | `mattpocock/skills` (grill-me, tdd, improve-codebase-architecture, to-spec, implement, code-review, handoff, diagnosing-bugs, codebase-design) + Anthropic `frontend-design` |
| Custom agents | `project-architect`, `test-author`, `architecture-scout`, `mvp-reviewer` — see `docs/AGENT_PIPELINE.md` |
| MCP | GitHub, Context7, Railway |
| Git | `gh` CLI |
| LLM (product) | TBD before MVP 3 — Gemini Flash / Claude Haiku / GPT-4o-mini |

---

## [Phase −1 · commit 1] Tooling setup, and two MCP servers that did not work

**Goal:** get the workflow in place before writing any application code — skills,
subagents, conventions, version control.

**Skills.** Installed via the `skills.sh` installer (`npx skills add
mattpocock/skills`) rather than the Claude Code plugin route. The installer writes
editable files I own into `.agents/skills/` and symlinks them into `.claude/skills/`;
the plugin route gives a managed read-only bundle. Chose the installer so the skills
can be adapted to this project if needed.

**Custom subagents.** Wrote four, in `.claude/agents/`. The organising idea is that
**authorship and verification must never share a context**:

- `test-author` writes failing tests and may not touch `src/`
- the implementer may not edit `tests/`
- `architecture-scout` and `mvp-reviewer` have no write tools at all

Without that split, one context writes a test, then quietly softens it to get green.
The separation makes TDD structurally enforced rather than aspirational.

Deliberately **not** delegated to agents: the `/grill-me` sessions (a subagent
interviewing itself reaches the conclusion it already held), this log, and the
review gate.

### The MCP servers

**`context7` failed with `ENOENT`.** The plugin runs it as a local subprocess via
`npx`, and Node was not on the PATH of the process that launched Claude Code —
the usual nvm symptom. Rather than fix the PATH, switched to Context7's hosted
endpoint (`--transport http https://mcp.context7.com/mcp`), which removes the local
Node dependency entirely. Connected.

**`github` failed with `HTTP 400` at `api.githubcopilot.com/mcp/`.** Different
failure: the server was reachable and rejected the request, so an auth problem
rather than a plumbing one. Rather than keep debugging, checked whether the MCP was
load-bearing at all — it is not. `git` plus the `gh` CLI covers every operation the
workflow needs (branches, worktrees, PRs, tags, releases), and Claude Code drives
both through Bash. Authenticated `gh` instead and moved on. The MCP later connected;
by then it was a convenience rather than a dependency.

**The lesson worth recording:** the reflex is to fix the broken tool. The better
question was whether the tool was needed. Roughly an hour of the budget was
recoverable by asking it earlier.

### Data strategy decision (before any code)

Audited the 11 seed records before writing anything. Ten distinct defect classes,
documented in `docs/DATA_AUDIT.md`. Two decisions taken here:

1. **Ingestion quarantines, it does not drop.** Invalid rows go to
   `hardware_quarantine` with a reason. The alternative — silently discarding the
   duplicate `id: 4` and the `"Unknown"` status record — loses information a
   reviewer would reasonably want to see handled.
2. **The semantic contradictions stay in the database.** The Dell XPS marked
   `Available` with "battery swelling" notes, and the MacBook Air marked
   `Available` with liquid-damage history, are not cleaned up. They are what the
   MVP 3 Inventory Auditor exists to find.

### Repo hygiene

The skills installer vendored 34 skills (~140 files) into the repo. Initially
planned to commit them as evidence of tooling. Reversed that: commit 1 would have
been 140 files of someone else's code with my ten buried inside, and the brief
grades commit-history quality. `skills-lock.json` gives exact provenance and
restores the set with `npx skills experimental_install`, at no diff cost.
`.agents/skills/` and `.claude/skills/` are gitignored.

**Commit:** `chore: project setup — agents, conventions, skills lockfile`

---

## [Phase −1 · commit 3] CORRECTION — I built a safety hole and called it a demo

**Prompt:** `/grill-me` at whole-project scope, against `brainstorm.md` v1,
`CONTEXT.md` and `CLAUDE.md`. I explicitly asked it to attack my seed-data plan.

**Tools:** Claude Code + `/grill-me` → `/grilling` (mattpocock/skills). Full
transcript in `docs/PROMPT_TRAIL.md`.

**What I had planned:** The seed contains two records whose status contradicts
their own free text — the Dell XPS 15, `Available`, notes reading "battery
swelling, do not issue without service"; and the MacBook Air M2, `Available`,
history recording liquid damage. I decided to leave both in the database
untouched, so the MVP 3 Inventory Auditor would have something real to find. I
wrote that down as a deliberate decision and was pleased with it. It was going to
be the best moment in the demo.

**What was wrong:** In the next phase I was going to build a rental engine whose
entire premise is that guards make impossible states unreachable. That engine
would have rented out the laptop with the swelling battery. Not as an edge case —
as its designed, correct, tested behaviour, because the item's status said
`Available` and nothing in the system disagreed.

I had preserved the contradiction for the AI to discover and left the product
free to act on the wrong half of it in the meantime. `needs_review` existed, but
it was a badge in an admin queue; it changed nothing about what the system would
allow. A flag that changes nothing is decoration.

Stated plainly: I subordinated product safety to a demo moment, and I wrote it
into the plan as a feature. If a reviewer had found this before I did, the
sentence would have been "you shipped a rental system that issues known-dangerous
hardware so your AI would look good", and I would have had no answer.

There was a second problem underneath it that I had not seen at all. "Battery
swelling" and "liquid damage" are keyword-findable. If my ingestion layer *could*
have caught them and I simply chose not to write that check, then I manufactured
the problem my AI exists to solve — which is the most damaging possible reading of
an AI-centred submission, and it would have been a fair one.

**How I caught it:** I didn't. The grilling did, on the first round, from the
question I had asked it to attack. I had written "attack that plan" expecting to
defend the quarantine-versus-delete choice, which is the part I had thought hard
about. The hole was somewhere I hadn't looked — not in how I handled the dirty
records, but in what the *next phase* would do with the ones I let through.

**The correction:** Two ADRs, because the flaw had two halves.

`ADR-0002` declares ingestion **structural-only** — schema, enum, keys, dates —
and puts semantic judgement explicitly outside its remit. That converts the
boundary from an accident into a position I can defend: deterministic validation
handles structure, the LLM handles judgement. It also commits me to something
uncomfortable, which is that the auditor has to flag record 10 (empty brand, null
date, unidentifiable) to prove it does anything a regex couldn't, and that the
README has to say out loud that a keyword scan would have caught the two obvious
ones.

`ADR-0003` makes `needs_review` a **rentability guard**: a flagged item returns
`409` through the same machinery that blocks renting an item in `Repair`. The
contradictory records stay in the database, stay visible, and stay unrentable. The
demo survives intact and the product stops being unsafe. Phase 0's quarantine work
stops being decoration and becomes the thing that makes Phase 2 correct.

**What I'm taking from it:** I was auditing the data and never asked what the rest
of the system would do with the data I chose to keep. The decision was defensible
in the phase where I made it and indefensible one phase later, and nothing in a
per-phase review would have caught that — which is the argument for grilling at
whole-project scope before any code exists, not per feature.

**Commit:** `docs: ADRs 0001–0005 from whole-project grilling` (pending)


---

## [P0 · c1] Scaffold and module skeletons

Backend scaffold plus signature-only skeletons: `app/config.py`, `app/domain.py`,
`app/main.py`, `scripts/seed.py`. Every function body raises `NotImplementedError`
— no logic, so the Phase 0 tests can fail on a real assertion rather than on
`ImportError`, which `CONTEXT.md` defines as broken rather than red. Vue/Vite,
vitest and CI are Phase 0 scope but not needed by the five backend tests; they are
deferred to a later Phase 0 commit.

Commit: chore(phase-0): scaffold and module skeletons (pending)

---

## [P0 · c2] Failing specs for seed ingestion and admin bootstrap

`test-author` against `brainstorm.md` §2/§3 and ADRs 0001, 0002, 0003, 0005.
18 tests, all red on `NotImplementedError` from the skeletons — no import errors,
which `CONTEXT.md` defines as broken rather than red.

The run surfaced three spec gaps I had not seen, and resolving them changed the
plan rather than the tests. §2 said the `"Appel"` typo was normalised at ingestion,
which contradicts ADR-0002 in the plan's own words: parsing a date field is
structural, correcting a spelling is judgement. ADR-0002 now draws that line
explicitly and §2 hands the typo to the auditor. The off-enum status had no
specified target — it maps to `Available` + `needs_review`, not `Repair`, because
`"Unknown"` says unidentifiable and `Repair` would assert a physical fact nothing
evidences. ADR-0005 now names `ENVIRONMENT` and states the permissive-local /
strict-production asymmetry it had implied twice without ever writing down.

Commit: test(phase-0): failing specs for seed ingestion and admin bootstrap (pending)

---

## [P0 · c3] Seed data, verbatim from the brief

`data/seed.json` copied byte-for-byte — verified by sha256 against the source, not
re-typed. Every defect is intentional test input and the file is treated as
read-only from here: 11 records, 10 unique ids, `4` twice, no `8`, matching all ten
rows of `brainstorm.md` §2.

Commit: chore(phase-0): add seed data verbatim from brief (pending)

---

## [P0 · c4] Quarantine importer and admin bootstrap

`/tdd` green pass against the 18 red specs. 18/18 pass, `tests/` untouched, no
corrections needed. Ingestion stayed structural: no keyword scan, `"Appel"`
preserved, the Dell XPS and MacBook Air imported `Available` and unflagged.

Run against the real `data/seed.json` it reproduces §2's audit exactly — 11
imported, 2 quarantined, and the duplicate re-keyed to 12 with `source_id: 4`,
which is the id §2 predicted before the code existed.

One gap the green pass exposed rather than closed: resolving the orphan rental
(id 2, `In Use` with nobody assigned) releases it to `Available` and leaves no
record of the change. Every other divergence from the seed is written to
quarantine with a reason; this one is not, so the database silently disagrees with
the brief about one row. §2 row 9 says only "resolved at import", so the
implementation matches the spec and the spec is what is thin. Flagged, not fixed.

Commit: feat(phase-0): quarantine importer and admin bootstrap (pending)

---

## [P0 · c5] Orphan rental audit trail and seed fidelity specs

Two red specs from `test-author`, closing the gap the green pass exposed. Committed
red, deliberately: the second one changes an interface decision and I wanted the
failure in the history rather than only its fix.

`test_seed_records_orphan_rental_in_quarantine` settles the spec thinness in §2
row 9 — releasing id 2 is a divergence from the brief, so it leaves a quarantine
record, but no `needs_review`. The item is usable; we simply cannot say who held
it, and flagging it would make a working MacBook unrentable over missing paperwork.

`test_importer_reproduces_documented_audit` runs the real `data/seed.json` rather
than a fixture, so `docs/DATA_AUDIT.md` becomes falsifiable. Every other test in
the file builds its own row, which keeps failures legible but means none of them
would notice the seed and the importer drifting apart.

The finding is mine to own: I made quarantine emission and `needs_review` the same
signal in c4 — one `reasons` list driving both. The orphan rental is the first case
where they must diverge, so the cheap fix turns the audit test green and leaves the
orphan test red on exactly the assertion written to catch it. The test-author
separation earned its keep here; the implementer could not have quietly widened the
test to fit the code.

Commit: test(phase-0): orphan rental audit trail and seed fidelity specs (pending)

---

## [P0 · c6] Separate quarantine audit trail from review flag

Green pass over the two red specs from c5. 20/20, `tests/` and `data/seed.json`
untouched. A `_Divergence(reason, needs_decision)` tuple splits the signal I had
collapsed: every divergence reaches the quarantine record, only undecided ones
reach `needs_review`. On the real seed that gives three quarantine records where
one — the released orphan rental — stays rentable.

**One instruction I did not carry out.** The brief said items should stop carrying
`review_reason` entirely: the record holds the narrative, the flag holds the guard.
But `test_seed_quarantines_unknown_status` was already green asserting a flagged
item carries its reason, "or the admin queue is blind", and I am not permitted to
edit `tests/`. I narrowed the field instead — `review_reason` is now populated only
from undecided divergences, so it mirrors the flag rather than the record, and the
repaired-row case behaves as asked. The duplication that remains is real and
unresolved, and it is a design disagreement rather than an oversight: the queue
either carries the reason on the item it renders, or joins back to quarantine to
explain itself. Left for the human, because the test is the human's to change.

Commit: feat(phase-0): separate quarantine audit trail from review flag (pending)

---

## [P0 · c7] SQLite persistence specs

`test-author` against the `app/storage.py` skeleton — six red specs for the seam
between the pure importer and the database. The red state proves only that the
module is unimplemented: all six error identically in the fixture on
`create_engine_for`, so it cannot show any of them discriminates. Mutation testing
against a scratchpad implementation is what confirmed it — a `persist_commits`
mutant passes all five original tests and is caught only by
`test_persist_does_not_commit`, which is why that sixth test exists.

Commit: test(phase-0): SQLite persistence specs (pending)

---

## Correction #2 — I acted on every finding, and every finding was correct

**What happened:** the agent pipeline worked. `test-author` kept surfacing spec
gaps, interface friction and design consequences at a rate I did not anticipate —
the collapsed `needs_review` signal, the unpinned transaction boundary, the
`review_reason` duplication, the table-name constants that nothing could pin. Not
one of them was noise. I checked each before acting, and each held up.

**Why that was wrong:** I acted on all of them. Every decision was individually
defensible and the aggregate was not. Phase 0 now has a persistence layer with
caller-owned transactions, replace semantics specified rather than inferred, and 26
tests including a mutation-verified check that `persist` does not commit — and
visible product is still zero. No UI, no deploy, no `DATA_AUDIT.md`. Against a
four-to-five hour budget I spent the margin on a data layer that is better than the
brief requires, and the brief asks for a working application.

**How I caught it:** I asked what a reviewer would see if I ran out of time at that
moment, and the answer was a rigorous test suite attached to nothing they could
open. The suite is not the deliverable.

**The correction:** a standing rule in `CLAUDE.md` — non-blocking findings go to
`BACKLOG.md` and work continues. Only something that makes the current work *wrong*
interrupts. `BACKLOG.md` is now seeded with the ten-odd items I would otherwise
have stopped for, each with a note on when it actually becomes urgent.

**What I'm taking from it:** the thoroughness was never the problem. The missing
piece was a filter on which correct observations deserved action *now*. Engineering
judgement is not only spotting the gap — it is knowing which gaps to write down and
walk past. I had no mechanism for deferring a legitimate finding, so every
legitimate finding became work.

Commit: docs: findings discipline rule after Phase 0 scope drift (pending)

---

## [P0 · c8] SQLite persistence for items and quarantine

`/tdd` green pass over the six storage specs. 26/26, `tests/` untouched. SQLAlchemy
Core rather than the ORM — the domain objects are frozen dataclasses and mapping
them would add a layer that buys nothing at this size.

Verified the suite discriminates against *this* implementation and not only the
scratchpad reference it was written against: with `persist` patched to commit via a
pytest plugin, 1 failed / 5 passed — only `test_persist_does_not_commit`. The
repo was not modified to run that check.

Commit: feat(phase-0): SQLite persistence for items and quarantine (pending)

---

## [P0 · c9] Vue scaffold, API, and single-origin wiring

Minimal frontend — one page, one fetch, a legible table, no router and no state
library. Two new tests: the bundle mount, which had been structurally present and
unexercised since c1, and `/api/hardware`, which is production code and so needed a
red test first. 28/28.

Also the Dockerfile and `python -m scripts.seed`, both needed before anything can
deploy. Findings from the pass went to `BACKLOG.md` rather than becoming work.

Commit: feat(phase-0): Vue scaffold, hardware API, single-origin wiring (pending)

---

## [P0 · c10] Seed on boot when the database is empty

`/tdd`. Two red specs first: an empty database seeds, a populated one is left
untouched. 30/30.

The second test is the one that matters. `persist` has replace semantics, so an
unguarded boot seed would wipe the table on every restart — the emptiness check is
what makes this safe rather than merely convenient, and once the rental engine
exists the table is never empty, so the seeding branch can never reach live data.

Chosen after `railway ssh` turned out to need an SSH key the machine did not have,
following `preDeployCommand` silently not executing across two deploys and
Railway's API exposing no exec. Recorded in `BACKLOG.md` as a deploy shim rather
than a migration strategy, because that is what it is: boot logic that writes data
couples "the process started" to "the data changed", and it will race itself the
moment there is a second replica.

Commit: feat(phase-0): seed on boot when the database is empty (pending)

---

## [P0 · c11] README, live-versions table, and visible boot logging

v0 is live at https://hardware-hub-production-24b7.up.railway.app with all 11
items and every seed fingerprint intact — id 12 re-keyed from the duplicate,
ids 6 and 10 flagged, `"Appel"` preserved, id 2's orphan rental released.

**A gap the tests could not have caught.** The boot-seed log line was emitted and
asserted, and never appeared in production: under uvicorn the root logger has no
handler, and `caplog` captures propagated records regardless of handlers, so the
test passed while the real deployment was silent. Found by reading the deploy logs
for a line that should have been there and was not. `create_app` now calls
`basicConfig`. The lesson is narrow and worth keeping: a passing assertion that a
log was *emitted* says nothing about whether anyone will ever *see* it.

Commit: docs(phase-0): README with live v0, and make boot logging visible (pending)

---

## [P0 · c12] Data audit

`docs/DATA_AUDIT.md`, transcribed from the green suite rather than from the plan —
every figure came out of running the importer over the real seed, not from
`brainstorm.md` §2's predictions. The last Phase 0 documentation deliverable.

One correction to the brief I was given: the re-key is *not* one of the three
quarantine records. Nothing is rejected when a duplicate id is repaired, and
`test_seed_rekeys_duplicate_id` asserts the quarantine table stays empty for it.
The three records are ids 2, 6 and 10. The document says so, and separately lists
the four rows where stored data differs from the seed.

Commit: docs(phase-0): data audit (pending)

---

## [P1 · c1] Wireframe justification scaffold

The wireframes are Booksy's, the brief marks them confidential, and this repo is
public — so `docs/wireframes/` is gitignored and they stay on the local machine.
Ignored before anything was staged; `git log --all -- docs/wireframes` is empty, so
nothing needs scrubbing from history.

The document that replaces them has to carry the weight the images would have:
every entry describes what the original showed before saying what was built
instead, so it can be judged without them. Recorded in the README's ⚡ section
rather than left as a silent omission.

Commit: docs: wireframe justification scaffold (pending)

---

## [P1 · c2] README status sections renamed to the brief's four

The four headings now read exactly as the brief names them, which forced a
redistribution: my "⚡ Partial" had been holding both shortcuts and absences, and
they are different claims. Anything that works but cost something is a shortcut;
anything that does not exist is missing. The wireframe omission carries both a Why
and a Future, like every other trade-off.

Correcting the headings surfaced a stale figure next to them — the summary said 28
tests where `pytest --collect-only` counts 30, from the two boot-seed specs in c10.
The status block is the part of the README a reviewer trusts most and verifies
least.

Commit: docs: align README status sections with the brief (pending)

---

## [P1 · c3] Phase 1 red — auth, admin guards, dashboard

`test-author` against `brainstorm.md` §3 and ADRs 0001, 0003, 0005. The nine named
specs plus a tenth for the session cookie: §3 lists the cookie as Phase 1 scope and
no named test touched it, and ADR-0001's whole payoff here is that `SameSite` is
free under single origin — free is not the same as set. 41 tests, 29 green, 11 red,
no `ImportError`.

**A spec contradiction the red state exposed.** The new tests read `/api/hardware`
anonymously, because Phase 0's green tests do. `test-author` refused to change that
on its own authority — turning a green Phase 0 test red is not a test author's call
— and filed it as an open question instead. It was right to ask, and the answer was
that my Phase 0 endpoint contradicted the brief: only admin-created accounts use the
Hub, so a public inventory endpoint was wrong the day I shipped it, not wrong now.
The endpoint is session-only. Three Phase 0 tests read it and all three are amended.

The judgement inside that change is the part worth recording. Two of the three are
the boot-seed pair, whose subject is what boot did to the table — not who may read
it. They now read through `app.storage` rather than over HTTP, because giving them a
login would have made two seeding tests unrunnable until auth exists and coupled
every future auth regression to a seeding failure. `test_inventory_requires_a_session`
pins the new rule on its own, and `test_serves_built_bundle_at_root` still fetches
`/` unauthenticated — so the tempting implementation, one middleware refusing
everything, turns a green test red and the login page stays reachable by
construction.

One cost I am not going to describe as free: no test now proves that *boot-seeded*
rows reach the wire. The pair that used to show it incidentally reads the table
directly, and `test_api_returns_hardware_items` seeds its own database rather than
booting into one. The two halves are each covered and the join is not — which on the
deploy path is exactly the join that runs. Written to `BACKLOG.md` rather than fixed,
because the seam is one `load_items` call wide.

`ADR-0006` records the decision, and leads with what was actually wrong rather than
with the brief: the endpoint was publishing the Dell XPS's "battery swelling" note and
the MacBook's liquid-damage history to anyone with the URL. The brief's rule is the
citation, not the argument. The reversal is also in `BACKLOG.md` as resolved rather
than deleted, with all five test consequences listed. Seven of the eleven
red tests now fail in fixture setup rather than on their own assertion, because they
sit behind a login that does not exist — so login is the first green commit, and the
suite gets re-read there to confirm every test fails for its own reason.

Commit: test(phase-1): failing specs for auth, admin guards and the dashboard (pending)
