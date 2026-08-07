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

## [Phase −1 · commit 2] Conventions, domain language, and this log

**Backfilled at Phase 1's review gate.** This commit — `14313c7`, *docs: project
conventions, domain language, AI log* — shipped without an entry, and an audit against
`git log` at the Phase 1 gate found it: 24 commits, 22 entries, and the numbering here
jumps from commit 1 to commit 3 because of it. `CLAUDE.md` says no entry means not done,
so the honest fix is an entry that says it was written late rather than one pretending
otherwise.

What the commit contained: `CLAUDE.md` (the non-negotiables), `CONTEXT.md` (the domain
language — "quarantine record", not "the row we couldn't import"), and this file's own
scaffold. No application code. The one decision worth recording is that the vocabulary was
fixed *before* the schema, which is why `needs_review` and `hardware_quarantine` read the
same way in the tests, the ADRs and the UI.

The other commit with no entry is `168048c`, the Phase 0 merge PR, which is a merge commit
and gets none by design.

Commit: docs: project conventions, domain language, AI log (14313c7)

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

**Commit:** `docs: plan v2 — four phases, ADRs 0001-0005 from whole-project grilling` (f5e669b) — written here in advance as *docs: ADRs 0001–0005 from whole-project grilling*; the commit shipped under the longer subject, and the difference is left visible rather than tidied.


---

## [P0 · c1] Scaffold and module skeletons

Backend scaffold plus signature-only skeletons: `app/config.py`, `app/domain.py`,
`app/main.py`, `scripts/seed.py`. Every function body raises `NotImplementedError`
— no logic, so the Phase 0 tests can fail on a real assertion rather than on
`ImportError`, which `CONTEXT.md` defines as broken rather than red. Vue/Vite,
vitest and CI are Phase 0 scope but not needed by the five backend tests; they are
deferred to a later Phase 0 commit.

Commit: chore(phase-0): scaffold and module skeletons (8e1501b)

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

Commit: test(phase-0): failing specs for seed ingestion and admin bootstrap (b4f8e61)

---

## [P0 · c3] Seed data, verbatim from the brief

`data/seed.json` copied byte-for-byte — verified by sha256 against the source, not
re-typed. Every defect is intentional test input and the file is treated as
read-only from here: 11 records, 10 unique ids, `4` twice, no `8`, matching all ten
rows of `brainstorm.md` §2.

Commit: chore(phase-0): add seed data verbatim from brief (8a25b0f)

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

Commit: feat(phase-0): quarantine importer and admin bootstrap (43c15ba)

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

Commit: test(phase-0): orphan rental audit trail and seed fidelity specs (a22b083)

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

Commit: feat(phase-0): separate quarantine audit trail from review flag (a10ba75)

---

## [P0 · c7] SQLite persistence specs

`test-author` against the `app/storage.py` skeleton — six red specs for the seam
between the pure importer and the database. The red state proves only that the
module is unimplemented: all six error identically in the fixture on
`create_engine_for`, so it cannot show any of them discriminates. Mutation testing
against a scratchpad implementation is what confirmed it — a `persist_commits`
mutant passes all five original tests and is caught only by
`test_persist_does_not_commit`, which is why that sixth test exists.

Commit: test(phase-0): SQLite persistence specs (9963791)

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

Commit: docs: findings discipline rule after Phase 0 scope drift (29779c2)

---

## [P0 · c8] SQLite persistence for items and quarantine

`/tdd` green pass over the six storage specs. 26/26, `tests/` untouched. SQLAlchemy
Core rather than the ORM — the domain objects are frozen dataclasses and mapping
them would add a layer that buys nothing at this size.

Verified the suite discriminates against *this* implementation and not only the
scratchpad reference it was written against: with `persist` patched to commit via a
pytest plugin, 1 failed / 5 passed — only `test_persist_does_not_commit`. The
repo was not modified to run that check.

Commit: feat(phase-0): SQLite persistence for items and quarantine (5f5893e)

---

## [P0 · c9] Vue scaffold, API, and single-origin wiring

Minimal frontend — one page, one fetch, a legible table, no router and no state
library. Two new tests: the bundle mount, which had been structurally present and
unexercised since c1, and `/api/hardware`, which is production code and so needed a
red test first. 28/28.

Also the Dockerfile and `python -m scripts.seed`, both needed before anything can
deploy. Findings from the pass went to `BACKLOG.md` rather than becoming work.

Commit: feat(phase-0): Vue scaffold, hardware API, single-origin wiring (a08a503)

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

Commit: feat(phase-0): seed on boot when the database is empty (74c38f6)

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

Commit: docs(phase-0): README with live v0, and make boot logging visible (3efe885)

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

Commit: docs(phase-0): data audit (9e1d9cb)

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

Commit: docs: wireframe justification scaffold (36ec0b4)

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

Commit: docs: align README status sections with the brief (3121790)

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

Commit: test(phase-1): failing specs for auth, admin guards and the dashboard (0b0bd7e)

---

## [P1 · c4] Login, session cookie, admin guards, dashboard

`/tdd` green pass over the eleven red specs. 41/41, `tests/` untouched, standard
library only for the credential path — `hashlib.scrypt` with a per-account salt, an
HMAC-signed cookie, no new dependency.

Two decisions taken rather than asked. **The enforcement point** (`brainstorm.md` §7)
is per-route dependencies, not middleware: a global refusal takes `/` down with it and
`test_serves_built_bundle_at_root` is green, so the wrong shape fails a passing test
rather than shipping. **The last-admin guard lives in `app/guards.py`**, not in a
handler — ADR-0005 puts it in the same layer as the rental guards, and one `_enforce`
helper turns a `GuardViolation` into `409` with its reason intact, so Phase 2's rent
and return find a layer instead of a precedent of inline `if` statements.

Commit: feat(phase-1): login, session cookie, admin guards and dashboard (180329c)

---

## [P1 · c5] Trim the working documents

`CLAUDE.md`, `CONTEXT.md` and the three agent briefs replaced with shorter versions —
the pace rules were being paid for in tokens every turn. `BACKLOG.md` pruned to what is
still owed: the Phase 0 scope list, the `DATA_AUDIT.md` debt, the `StaticPool` and
`PRAGMA` constraints and the resolved session question are all deleted, because
`create_engine_for`, the audit doc and ADR-0006 now hold those answers. Entries are
deleted when done rather than annotated; the reversal record lives in `AI_LOG.md` and
`docs/adr/`, not here.

Commit: docs: trim CLAUDE.md, CONTEXT.md, agents and backlog for pace (d26270f)

---

## [P1 · c6] The Phase 1 UI, and v1 live

Four screens against the supplied wireframes: login, the dashboard, the admin panel and
a `needs_review` queue. 47/47 green. Thirteen deviations recorded in
`docs/WIREFRAME_JUSTIFICATION.md` as they were made — the load-bearing ones being the
status labels (the enum's words, not the wireframe's "Rented / In Repair"), the dropped
Serial Number and Category fields (no such columns exist), and the dropped edit action
(no endpoint, and the wireframe's own button only raises a toast admitting it does
nothing).

**Two routes the wireframes required and §3 never specified.** "Add New Device" had no
`POST /api/hardware` behind it, and the `HttpOnly` cookie means a reloaded page knows it
has a session but not whose — so `GET /api/session`. Both got failing tests first, in new
files rather than by touching `test-author`'s green ones. Six new tests.

**The design decision worth naming:** `needs_review` is not a fourth status chip. A
flagged item still has a status — both flagged seed rows are `Available` — so two
orthogonal facts cannot share one cell. The flag gets its own column and an amber edge
marker on the row, which is what makes it scannable down a dense table without reading
every line.

**A correction, and it was mine.** Verifying the live deployment I sent
`DELETE /api/users/1` at production expecting the ADR-0005 guard to refuse it. It did not
refuse, correctly — I had just created a second admin for the demo account, so the guard
had nothing to protect — and I deleted the deployment's real bootstrap admin. Restored it
immediately from `ADMIN_PASSWORD` (it is id 3 now), and the inventory was never touched:
11 items, 2 flagged, seed ids intact. The lesson is not "be careful with DELETE". It is
that I ran a *destructive* probe to observe a *refusal*, against production, when
`test_cannot_remove_last_admin` already proves that behaviour locally and its control
covers exactly the two-admin case I had accidentally created. A test that passes is not a
reason to re-run the experiment by hand on live data.

v1 is live on the Phase 0 URL, verified signed in as the published demo account. The
cookie comes back `HttpOnly; SameSite=lax; Secure`, anonymous requests to
`/api/hardware` and `/api/session` both get `401`, and the guard's `409` reason renders
verbatim in the UI for both the delete and the demote path.

Commit: chore(phase-1): deploy v1 (1dc0921)

---

## [P1 · c7] Security review triage

`/security-review` raised two code findings and both filtered out as false positives at
2/10: the dev `SECRET_KEY` fallback (the live service sets `ENVIRONMENT=production` —
provable from outside, because the session cookie comes back `Secure` and only that
branch sets the flag), and the `notes`/`history` exposure (this branch *narrowed* it from
anonymous to authenticated, and what remains is maintenance prose about laptops).

The genuinely exploitable thing was the item the review flagged as outside its own scope:
the README published an **admin** credential on a public instance, so any reader had
delete rights over the inventory and the account list. Demoted `demo@booksy.com` to
`user` on the live instance and verified all five admin routes now answer `403` to it,
inventory intact. This does not contradict ADR-0005, which requires *published demo
credentials* and never said they had to be admin. It cost the walkthrough: the admin
panel is no longer reachable from the published credential, and the README says where to
see it instead.

The three accepted items went to the README `⚠️ Partial / Missing` section with the
reason each was not fixed, rather than to `BACKLOG.md` — a reviewer reads the README, and
"we knew and chose not to" belongs where the claim is made.

Commit: fix(phase-1): demote published demo account to read-only (332b87a)

---

## [P1 · c8] Log audit against git

Audited both logs against `git log` rather than against memory. 24 commits, 22 entries —
two gaps: `14313c7` (backfilled above, and marked as backfilled) and `168048c`, the Phase 0
merge, which needs none.

`docs/PROMPT_TRAIL.md` was the real gap: last touched at commit 3 of 24, while ADR-0006,
the session requirement, the enforcement point and three other architectural decisions had
been taken since. The cause is visible in `CLAUDE.md`, which lists this file as "after every
grilling" — and Phases 0 and 1 have no grilling by design, so the trigger never fired. The
brief asks for the prompts that shaped the architecture, not grilling transcripts.
Backfilled as Part II, seven sessions, each marked *verbatim* or *reconstructed* and each
naming its commit. The Phase 0 ones are reconstructed and say so; inventing wording would
have made the document worth less than the gap it filled.

One inconsistency this audit found and did not fix at the time: every entry ended
`(pending)` rather than the commit sha, including entries whose commits were long since
pushed, against `CLAUDE.md`'s own `(a1b2c3d)` example. Left for the human to sanction, and
sanctioned — backfilled in [P1 · c9] by matching each entry's stated message against
`git log`. Two did not match cleanly and are noted where they sit.

Commit: docs(phase-1): backfill prompt trail and audit both logs (0583244)

---

## [P1 · c9] Fixes from the MVP review, and the SHAs

`mvp-reviewer` at Phase 1's gate: PASS WITH NOTES, one blocker. 55/55 green.

**The blocker was a test gap, not a defect.** Deleting the `hmac.compare_digest` check in
`app/sessions.py` left the whole suite green — every test presented a cookie the server had
issued and none forged one. The signing code was right and nothing defended it, which
matters because Phase 2's wrong-user rental guard reduces entirely to trusting the account
id in that cookie. `tests/test_session_integrity.py` now forges five ways, including a
genuine signature moved onto another subject and a correctly signed cookie for a deleted
account. Both mutants that were previously green now fail five tests each. The first draft
of that test passed against a *broken* implementation for an embarrassing reason: I forged
subject `1`, and the bootstrapped admin is account 1, so my "forgery" was the real cookie.

**Two were real defects.** `add_item` read `max(id)` then inserted, so six concurrent
`POST /api/hardware` calls raced and one died on the primary key — the id is now chosen by
a subquery inside the `INSERT`, so SQLite evaluates it under the write lock. Fixed here
rather than filed because Phase 2 is entirely about concurrency and this module is what its
rental engine will hold a transaction on. And `Field(min_length=1)` accepted `"   "`, which
is precisely the unidentifiable row seed record 10 exists to demonstrate; names are now
trimmed before length is checked.

**One was a documentation trap.** `demo@booksy.com` existed only inside the Railway volume,
created once by hand — so a replaced volume would leave the README publishing credentials
that authenticate nothing, silently, with the app booting fine. It is now bootstrapped like
admin #1 under the same emptiness guard as the hardware seed, as a `user`, and the test
asserts the published password *by logging in with it* rather than by checking a row exists.
The second test is the one that matters: a deliberately deleted demo account must stay
deleted across a restart, or the published credential could never be revoked.

**One needed no fix.** The privilege-escalation routes were already guarded — a `user`
cannot self-promote through `PATCH /api/users/{own_id}`, because `Depends(current_admin)`
refuses it. The review's point was that nothing *pinned* that, so
`tests/test_privilege_escalation.py` now does, checking the role by consequence after each
refusal rather than trusting the status code. Reported as tests added, not as a hole closed.

**Owning the mislabel:** `1dc0921` is `chore(phase-1): deploy v1` and should have been
`feat:` — ~1,600 lines of frontend and two new API routes with their tests, all in one
commit, which also hid a red-then-green cycle for exactly the two routes whose test-first
claim cannot otherwise be checked from history. It is pushed and it stays. Rewriting history
so the log looks tidier is the failure mode this project is graded against, and a visible
bad commit with a note is worth more than an invisible one.

All 25 entries now carry their commit sha instead of `(pending)`.

Commit: fix(phase-1): session integrity, add-hardware race, demo bootstrap (4f9b07c)

---

## [P2 · c1] Phase 2 owns clearing `needs_review`

Phase 1 merged (PR #2, tagged `v1-admin`) with one piece of its own scope unresolved: the
queue is surfaced and nothing clears the flag. ADR-0003 had said that must not reach the
Phase 2 gate, which it now has — so it is resolved *by assignment* rather than left to
read as overdue.

The reason Phase 2 owns it is structural, not scheduling. `needs_review` is a rentability
guard, so clearing it is a transition in the same state machine as rent and return.
Bolting a clear-flag button onto the Phase 1 admin panel would have put transition logic
in a route handler, which is the exact failure ADR-0003's last consequence warns about
and which `brainstorm.md` §3 calls the load-bearing risk for the Phase 2 architecture
pass.

ADR-0003 gains a Consequences entry naming three requirements — admin-only action, audit
trail, gated on `app/guards.py` — and two tests, `test_admin_can_clear_needs_review` and
`test_cleared_item_becomes_rentable`. The second is the one that matters: a flag that
clears but still blocks rental is the same decoration this ADR was written to remove, in a
new place. `brainstorm.md` §3 Phase 2 carries both in its test list; `BACKLOG.md` moves the
entry from "urgent before the Phase 1 gate" to an *Owned by Phase 2* section; the README
says it in `⚠️ Partial`, and three other places that still said "due before the Phase 2
gate" now agree with the ADR.

Commit: docs(phase-2): assign the clear-flag mechanism to Phase 2 (7ae6eac)

---

## [P2 · c1a] Grilling 2, six ADRs, and the phase spec

**Backfilled at the pre-submission doc audit, 2026-08-07** — the second entry in this log
to be written late, and labelled so for the same reason as the first. `a44f85f` shipped
grilling 2's output (ADR-0007–0012, the ADR-0003 amendment, `docs/specs/phase-2.md`) with
no entry; `mvp-reviewer` caught it at the gate, and the pre-commit hook that would have
refused it landed two commits *later* — this is the one gap the hook postdates. The
session itself is in `docs/PROMPT_TRAIL.md` Session 9, recorded in the moment; only this
pointer to it was missing. Numbered c1a because every later entry was already numbered
when the gap was found.

Commit: docs(phase-2): grilling 2, six ADRs, and the phase spec (a44f85f)

---

## [P2 · c2] Phase 2 red — slices A and B

`test-author` against `docs/specs/phase-2.md` and ADRs 0003 (amended), 0007–0012.
28 red, 55 still green, nothing failing for the wrong reason — no `ImportError`, because
the tests drive HTTP rather than importing an `app/rentals.py` that does not exist. Two
retrofit tests fail by *demonstrating the defect*: `PATCH /api/hardware/7 {"status":
"Repair"}` returns `200` on a held item today, and `DELETE /api/hardware/7` returns `204`.

**A gap the grilling missed, closed here.** ADR-0011 says `persist` refuses when rentals
exist; ADR-0007 says seed id 7 is imported as a rental; `test_reseed_is_idempotent` calls
`persist` twice and is green. All three hold only if the seed rental is written by
`scripts/seed.py` *above* `persist`, which keeps `persist` a pure row-mover and is what the
spec's own "replace semantics must never reach it" already implied. Pinned in the new
test's docstring so the constraint is discoverable from the test rather than inferred.

**No existing test needed changing.** I had expected three; the answer was none. The two
retrofit guards cannot fire against seed item 1, which is `Available` with no rental, so
`test_admin_can_toggle_repair_status` and `test_non_admin_cannot_delete_hardware` stay
true — ADR-0009 says as much itself ("needs a companion, not a change"). The companions
are new tests.

**And ADR-0003 contains a false sentence**, found by writing the test it describes: it says
`test_cannot_rent_flagged_hardware` asserts "the Dell XPS specifically remains unrentable",
but ADR-0002 makes ingestion structural-only, so the Dell XPS imports `Available` and
**unflagged**. The flagged rows are ids 6 and 10. The test derives the flagged set from the
inventory instead, which covers both and survives Phase 3 flagging more. Filed rather than
escalated — it changes no behaviour, only a claim.

Commit: test(phase-2): failing specs for the rental engine and the review flag (3629b17)

---

## [P2 · c3] The AI log becomes a commit gate

`hooks/pre-commit` refuses any commit that does not stage `AI_LOG.md`, and prints the two
formats rather than just failing. Wired with `git config core.hooksPath hooks` and
committed to the repo, because `.git/hooks/` is not versioned and does not survive a
clone — the README carries the one-line setup.

The reason it is a gate and not a convention: the convention held for 24 commits because I
remembered it, and the Phase 1 audit found the two places I had not. Merges and
`--no-verify` still pass, the second deliberately.

`conductor`'s standing checks now cover the two things a per-commit hook cannot see —
`docs/PROMPT_TRAIL.md` drifting behind the ADRs (count one against the other; it was 21
commits behind when first audited), and work visible in the diff that never reached the
README's four graded sections.

Commit: chore: enforce AI log as a commit gate (87167d1)

---

## Correction #3 — I wrote the brief that made the agent slow

**What I observed.** `test-author` was taking about twenty minutes a phase and producing
far more than I asked for: 18 tests in Phase 0, and 11 in Phase 1 against a named list of
nine. The suite is now at 55 tests — 83 with Phase 2's red pass — for a brief that asked
for three critical ones. None of the extra tests are bad. Several are the best tests in the
project. That is what took me so long to see the problem.

**What I diagnosed.** The agent brief was the cause, not the agent. Two lines did it. The
first was *"the named test list is your floor, not your ceiling"* — which is not a
permission to expand, it is an instruction to. The second was the input list: the phase
spec, `brainstorm.md`, the relevant ADRs, and every existing test file, all read before
writing a line. I specified thoroughness in the inputs and again in the scope, and
thoroughness is exactly what I got, on time, every time.

**What I changed.** One input file instead of four. *"Write exactly the named list"* in
place of the floor-and-ceiling line. A hard cap of twelve tests. Mutation testing banned
outright — it earned its keep once, on `persist`, and became a tax everywhere else. A
five-line cap on the report.

**Why it is the right trade here.** Coverage is already well past what the brief asks for,
and the binding constraint on this project is time, not rigor. Cutting the agent's reading
list costs me tests I would probably never have missed, and buys back the minutes that
Phase 2's three slices need. If I were building this to run in production rather than to be
read in a review, I would revert every one of these changes.

**What I am taking from it.** This is the same lesson as Correction #2, which is the part
worth writing down. There, every finding the pipeline surfaced was correct and I acted on
all of them, and the aggregate was wrong. Here, every test the agent wrote was justified by
the brief I gave it, and the aggregate was wrong. Both times the agent did exactly what I
told it to. Both times I looked at the output first and the instruction second. Second time
in one project — the reflex I need is to read my own brief before I read the agent's work,
because if the output is consistently off in one direction, the instruction is where the
direction came from.

Commit: chore: tighten test-author brief for pace (253b254)

---

## [P2 · c4] Phase 2 green — the rental engine and the review flag

`/tdd` over the 28 red specs. 83/83, `tests/` untouched. `app/rentals.py` owns the
transitions and their SQL (ADR-0008), `app/audit.py` owns the one override table
(ADR-0010), and both keep their own `MetaData` so `persist`'s replace semantics can never
reach them.

**Two SQLite lessons, both found by the suite hanging rather than failing.** The rent
route read the item to run guards and *then* issued the atomic `UPDATE` — six concurrent
claimants each holding a read lock and trying to upgrade it deadlock instead of
serialising, and the suite sat there until I killed it. Inverting it fixed the hang and is
the better design anyway: attempt the claim, and read the row only to explain a failure.
That is what ADR-0008 already says — the statement is the decision, the guards are the
message — so the deadlock was the code disagreeing with its own ADR.

The second: `_open_seed_rentals` ran `CREATE TABLE rentals` on a second connection while
the seeding session held a write transaction. SQLite refuses, and the error surfaced as a
fixture error in an unrelated test. DDL now runs on the engine before any session opens.

The `persist` refusal is deliberately ignorant: it checks `sqlite_master` for the table and
then for a row, so it survives the engine every storage test builds, where `rentals` has
never existed. `app/storage.py` still knows nothing about what a rental *is* — only that
rows in that table mean the inventory is not replaceable.

Commit: feat(phase-2): rental engine, clear-flag and audit trail (07120d4)

---

## [P2 · c5] Slice C — the rental verbs on the dashboard

`frontend-design`, against the Phase 1 aesthetic rather than a new one: same tokens, same
table, one reused dialog. 86/86 — `?held_by=me` needed a route, so it got three red tests
first in a new file before any UI existed.

The one design decision worth naming: **a row that cannot be rented says why, instead of
showing a greyed-out button.** The wireframe greys the button; the row already knows
whether it is `Repair`, held, or flagged, and those are three different facts. The brief
asked for a `409` to show its readable reason — this is that requirement moved one step
earlier, and the server's own message still arrives in a toast when a row goes stale
between paint and click.

**A keyboard bug the browser found and the code review would not have.** `autofocus` is
honoured on page load, not when an element is inserted later, so opening the reason dialog
left focus on the button that opened it and everything I typed went nowhere. Fixed with an
explicit focus on open plus `Escape` to cancel. The Phase 1 add-hardware dialog has the
same defect and is now in `BACKLOG.md` — worth noticing that a bug shipped in Phase 1,
survived a review gate, and was only caught by driving the thing.

Commit: feat(phase-2): rent, return and the admin overrides in the UI (5fc9bcb)

---

## [P2 · c6] Deploy v2, and the bug only the deploy could find

v2 live on the Phase 0 URL. 88/88.

**Two of the four flows I set out to verify could not be run, and that was the finding.**
Item 7 reported `In Use` and force-return answered "not currently rented": the ADR-0007
seed rental is opened inside `seed_if_empty`, which returns early on a database that
already has hardware — true of every volume that existed before Phase 2. So on the
upgraded instance the headphones were held by an address with no account *and* no rental
row. Unreturnable, because there was no rental to close. Unrecallable, for the same
reason. `CONTEXT.md`'s "In Use with no renter" impossible state, arrived at through a
deploy rather than through the seed.

Boot now reconciles held items on **every** start rather than only an empty one — the
opposite of how the seed is guarded, and deliberately: seeding writes inventory and must
never repeat, while this reconciles a row that already exists. Idempotent, so a restart
over a healthy database does nothing.

**My own test then caught a footgun in my own code.** It asserted that an account-scoped
query finds nothing for the accountless rental, and it failed — SQLAlchemy renders
`column == None` as `IS NULL`, so `item_ids_held_by(None)` matched seed id 7 and would
have handed it to whoever asked. Not reachable through the API, one line to close, and
exactly the shape of bug that becomes reachable later.

Worth stating plainly: this class of defect is invisible to a fresh-database test suite.
88 tests passed against a database that had never been upgraded, and the item was stranded
the moment the code met a real volume.

Commit: chore(phase-2): deploy v2 (3bce364)

---

## [P2 · c7] A repeatable demo reset, and a model change

**The reset.** Verifying v2 consumed the state the project is about — item 7 recalled,
both flags cleared. `POST /api/admin/reset-demo` clears rentals and audit events, then
reseeds. Three tests, 91/91.

Two decisions inside it. It is an **HTTP route rather than a CLI** because Railway exposes
no exec or SSH — the same constraint that put seeding on the boot path — so
`python -m scripts.reset` would have been documented for a deployment that cannot run it.
And it **clears the blocker rather than bypassing it**: ADR-0011's refusal is right and
stays, so the reset deletes rentals first and then reseeds through the same guard every
other caller meets. A `force=True` parameter on `persist` would have been three characters
shorter and would have removed the protection for everyone.

The confirmation phrase is a `Literal`, so a wrong one is a `422` from the model rather
than a branch somebody can forget.

**The tension it creates, filed rather than hidden:** this route erases the audit trail
ADR-0010 was written to protect, and nothing records that a reset happened. It has to
clear the events — a trail pointing at rental ids that no longer exist describes events
that did not occur — but "the most destructive route leaves no trace" is fine only because
this instance exists to be restored. In `BACKLOG.md`, with the condition that makes it
urgent.

Verified against the live instance and run twice: 7 rentals and 3 audit events cleared, 11
items and 3 quarantine records reseeded, 1 seed rental restored. Every fingerprint back —
ids 6 and 10 flagged, item 7 held by `j.doe@booksy.com`, id 12 carrying `source_id` 4, the
`Appel` typo intact, and the Dell XPS `Available` with its swelling-battery note.

**The model change.** `mvp-reviewer` now runs on Fable 5, and grillings use Fable 5 from
here. The reason is where reasoning depth actually pays: implementation is constrained by
a spec and a red test that either passes or does not, and a cheaper model reaching the
same green is the same result. Adversarial self-review and grilling have no such
backstop — nothing fails loudly when a reviewer misses the finding or a grilling asks the
comfortable question instead of the sharp one, and both are exactly where this project has
been saved twice already: the whole-project grilling caught the rentable-swelling-battery
hole, and `mvp-reviewer` caught a session signature that no test defended.

Put plainly: I am spending the deeper model at the two gates where a miss is silent, and
not on the loop where a miss is loud.

Commit: feat(phase-2): repeatable demo reset (139e262)

---

## [P2 · c8] Give ADR-0002's deferred typo an owner

`"Appel"` on seed id 9 is the one defect ADR-0002 explicitly declined to fix, on the
grounds that parsing a date is structural and correcting a spelling is judgement. That
argument only holds if something *does* eventually catch it — an unfixed typo that nothing
ever finds is indistinguishable from an oversight, which is the reading ADR-0002 was
written to prevent.

So Phase 3's auditor scope now names it, and `test_auditor_flags_misspelled_brand` pins
it. ADR-0002 points forward at both, so the deferral is traceable from the decision to the
test rather than living only in a sentence somebody has to remember.

Worth noting what it does *not* do: the auditor flags the brand as a probable misspelling.
It does not correct it. Correcting is still judgement, and the item still belongs to a
human.

Commit: docs(phase-3): the auditor owns ADR-0002's deferred typo (adca539)

---

## [P2 · c9] Soft-delete accounts, and stop signing a row id

`/security-review` at the Phase 2 gate, both findings reproduced end to end. 95/95.

**The defect underneath both was that `users.id` is a SQLite rowid alias.** No
`AUTOINCREMENT` keyword, so deleting the highest-id account frees its number and the next
account created is handed it. Three things were keyed on that number and all three broke:
a deleted `user`'s untouched cookie came back as the *replacement admin*; a departed
employee's active rental appeared in their successor's `?held_by=me` and could be closed
through the renter verb ADR-0009 calls absolute; and an `audit_events` actor became
whoever inherited the id.

The third is what chose the fix. ADR-0010 exists so "somebody inspected this and it is fit
to issue" can be interrogated later, and that is only truthful while actor identity is
stable. **An id that can be reissued is not an identity.**

So: sessions name a per-account token issued once and never reissued, and accounts are
soft-deleted — the row stays, `deleted_at` is set, the token is cleared, and every
authentication and listing read filters on it. Both columns are additive and backfilled on
boot, which is the reason this and not `sqlite_autoincrement=True`: that only affects
`CREATE TABLE`, so it would have left the deployed database exactly as vulnerable while
looking like a fix.

**Two consequences worth stating rather than discovering.** Existing live sessions
invalidate on this deploy — accepted, since there is no logout route and they had no other
way to end. And a deleted address cannot be reissued (`409`), which is correct rather than
incidental: the trail names actors by email as well as id, and reusing an address rebuilds
the same ambiguity one field over.

The FKs ADR-0011 claimed also now exist. They needed `ForeignKey(hardware.c.id)` rather
than the string — `rentals` and `audit_events` keep their own `MetaData` so `persist`
cannot reach them (ADR-0007), and a string target cannot resolve across that boundary.
That is why the belt was missing: declaring it required reconciling two ADRs, not adding a
keyword. And `current_account`'s docstring, which claimed a deleted account's session was
refused, is now true instead of aspirational.

Commit: fix(phase-2): soft-delete accounts and sign a session token (5d33b44)

---

## Correction #4 — "additive column" was a property of the column, not of the code

**What I shipped.** ADR-0013 adds `session_token` and `deleted_at` to `users`, and I
described them — in the ADR, the commit message and my report — as "additive columns,
backfilled on boot, no destructive migration on the live volume". Every word of that was
true about the *columns*. None of it was true about the *code*: `metadata.create_all()`
skips a table that already exists, columns and all, so nothing ever added them to the live
`users` table.

**What happened.** The deploy came up. The first request touched `users.deleted_at`, and
the instance answered `502` to everything for as long as it took me to notice — which was
the verification step immediately afterwards, because I was checking the fingerprints and
got JSON decode errors instead. It was down for roughly eight minutes.

**How I caught it.** The verification I was already running. That is the only part of this
I would repeat: the check was "log in fresh and confirm the seed fingerprints", not "did
the build succeed", so it exercised a request path rather than a deploy status. A smoke
test that asserts `200` on `/` would have passed — the static bundle serves fine, and the
failure was in the first query behind it.

**Why the tests did not catch it.** 95 of them passed, and every one built its database
from scratch, where `create_all` does create the columns. The entire suite was blind to
the only case that mattered: an *existing* table. This is the second time in two phases
that a fresh-database suite has been green against a defect that only exists on an
upgraded volume — the first was the seed rental that `seed_if_empty` never reconciled.
Two of the same shape is a pattern, not bad luck.

**The correction.** `create_schema` now inspects `PRAGMA table_info` and `ALTER TABLE …
ADD COLUMN`s what is missing, idempotently — checked by inspection rather than by
catching the exception, because `ADD COLUMN` fails if the column is present and a
migration that works exactly once is worse than none. `tests/test_schema_migration.py`
builds a `users` table in raw SQL in the shape Phase 1 shipped and boots over it, and it
asserts a *login* rather than that `create_app` returned — the production failure was at
first request, so a test that only booted would have been green while the instance was
still `502`.

**What I am taking from it.** I wrote "no destructive migration needed" and stopped
thinking, because the sentence was reassuring and I had chosen the design specifically to
earn it. The claim I should have checked was the adjacent one nobody had made: *is any
migration happening at all?* When a design decision is justified by what it avoids, the
thing to verify is that the alternative is actually being done.

Commit: fix(phase-2): migrate the users table on boot (4fc27c5)

---

## [P2 · c10] Migration tests become a non-negotiable

`CLAUDE.md` gains one rule: a schema change ships with a test that boots over the
*previous* table shape and asserts a real request, not that `create_app` returned.

It earns its place by having been paid for twice — the seed rental `seed_if_empty` never
reconciled on an existing volume, and Correction #4's missing `ALTER TABLE`. Both were
green across the whole suite, because every test in it builds its database from scratch,
which is the one condition under which `create_all` does the migration for you.

Also corrected the phase table in the same file, which still described Phase 1 as in
progress two tags later.

Commit: docs: migration tests are mandatory for schema changes (6e1216a)

---

## [P2 · c11] `architecture-scout` at the gate, and an invariant that was never as strong as its ADR

Verdict: sound enough to build Phase 3 on. Four findings, all filed, none fixed.

**The one that matters was a correctness claim, so I reproduced it rather than relaying
it.** `ensure_an_admin_remains` reads the admin count and writes in a separate statement;
two concurrent demotions of the final two admins both returned `200` and left **zero live
admins** — the state ADR-0005 exists to make unreachable.

My first attempt to reproduce it was wrong and I nearly reported the invariant as holding:
I demoted the bootstrap admin to get down to two, which turned the acting client into a
`user`, and read the resulting `403`s as the guard working. They were authorization. The
actor has to stay an admin through both requests for the race to be reachable at all.

Not fixed. The trigger is simultaneous demotions on a two-admin internal tool, and the fix
is already written down one ADR over — ADR-0008 settled that a read-then-decide guard
cannot win a race, for `rent`. What is worth recording is that the rental engine met this
exact problem three ADRs later, solved it properly, and nobody noticed the older guard
shared it. A single-guard framing hid a class.

ADR-0005 now says the invariant holds only under sequential access, which is what it always
meant rather than what it claimed.

Commit: docs(phase-2): file the architecture-scout findings (eec6b5b)

---

## [P2 · c12] mvp-reviewer red: the transition trusts its caller with its own record

`rentals.force_return` demands a mandatory `reason` (ADR-0010) and ignores it — the
audit write lives in the route, so any second caller ends a rental unrecorded. Red at
the direct call: 0 audit events.
Commit: test(phase-2): pin the audit write inside force_return (8f127df)

---

## [P2 · c13] The audit write moves into the transition

`audit.record` moves from the route into `rentals.force_return`, same transaction as
the close; the route-level "exactly one event" test proves nothing double-writes. 98/98.
Commit: fix(phase-2): force_return writes its own audit event (e77355d)

---

## [P2 · c14] The README stops describing Phase 1

mvp-reviewer's blocker: the graded sections said the rental engine did not exist, on the
branch that shipped it. Brought to v2 reality, Reseeding now points at the reset route
(ADR-0011), the 41-vs-15–20 commit count is acknowledged in ⚡ with its why, and the
four non-blocking findings are filed in BACKLOG.md.
Commit: docs(phase-2): bring the README to Phase 2 reality (eb5b20a)

---

## [P3 · c1] Pre-submission doc audit against the brief

Every `.md` checked against the brief's deliverables. AI_LOG: 17 SHAs back-annotated,
`a44f85f` backfilled as c1a. PROMPT_TRAIL: Sessions 12–13 close the ADR-0013 and
gate-review gaps — 13/13 ADRs now trace to a prompt. README: 🔮 lists three next steps,
seed-on-boot gets its Why/Future. BACKLOG drops three done/false entries; brainstorm.md
gets a dated status note instead of a rewrite.
Commit: docs(phase-3): audit every doc against the brief (1aff2db)

---

## [P3 · c2] Phase 4 — wireframe fidelity — enters the plan

New phase in `brainstorm.md` §3, after Phase 3, not started: close-copy UI fidelity,
three schema columns with the mandatory migration test, an ADR-0012 amendment (renter
hidden from non-admins) written rather than silently reversed, and two brief-mandated
wireframe deviations (Purchase Date, filtering) pre-registered for
`WIREFRAME_JUSTIFICATION.md`. §0, CLAUDE.md's phase table and the README (🔮 + a v4 row)
now agree there are five gates.
Commit: docs(phase-4): plan the wireframe-fidelity phase (b059470)

---

## [P3 · c3] Grilling 3, four ADRs, and the phase spec

Two rounds, frontier cut deliberately — flag-verb detail assigned to the spec, the
Session 9 precedent. ADR-0014–0017: propose-never-dispose, no restricted-field
predicates, announced degradation, and the flag-review verb ADR-0010 withheld.
Spec sliced A/B/C with hardening as a gate checklist.
Commit: docs(phase-3): grilling 3, four ADRs, and the phase spec (270df1d)

---

## [P3 · c4] `visible_to` moves to the domain, ahead of its two new callers

The architecture-scout finding executed on its own trigger: "urgent when a second
caller appears" — Phase 3 adds two (search, auditor). Pure move, `app/main.py` →
`app/domain.py`, plus one stale comment fixed (findings are never written into these
columns, ADR-0014). 98/98 before and after.
Commit: refactor(phase-3): move field visibility to the domain (082ac46)

---

## [P3 · c5] Phase 3 red — slices A and B

`test-author` against `docs/specs/phase-3.md` and ADR-0014–0017. 12 red on their own
assertions, 99 green, 0 broken — the bundle leak guard is green before the feature
exists, by design. Cut under the 12-cap: `test_auditor_flags_misspelled_brand`
(plumbing-identical to id 10's), filed in BACKLOG with the cost named — ADR-0002's
typo loop has no test until green adds it back.
Commit: test(phase-3): failing specs for semantic search and the inventory auditor (7ce8e05)

---

## [P3 · c6] Phase 3 green — slices A and B

`/tdd` against the red pass. 111/111, `tests/` untouched. One module (`app/ai.py`)
owns the schema and its SQL, per the ADR-0008 precedent; `extra="forbid"` on the
filter model is what makes the oracle rejection wholesale rather than salvaged.
The real Gemini client is built lazily so the socket-refusing suite never sees it.
Commit: feat(phase-3): semantic search and the inventory auditor (f126893)

---

## [P3 · c7] Slice C — the flag-review verb, and the finding that becomes a flag

Red first (6 tests, all failing on their own assertions), then green: `flag_review`
in storage as `clear_review`'s mirror, the action enum grows `flag_review`
(ADR-0017's own consequence), route `409`s an already-flagged item. UI: dashboard
search with the mode label shown (ADR-0016), auditor panel where each finding is a
button whose reason arrives prefilled and editable — the recorded claim is the
human's. 117/117.
Commit: feat(phase-3): admin flag-review verb (c516ce3)

---

## [P3 · c8] Deploy v3 — hardening at the gate

Health endpoint red-then-green (sessionless by design, touches nothing), bundle
grepped clean of the provider and any key, README at v3 reality, wireframe doc gains
the two AI surfaces. 118/118. Live verification after the push: smoke flow, one
semantic search, one audit run — the auditor's live judgment on ids 9 and 10 is the
claim the suite cannot make (mocked model), so it is checked on the deployment.
Commit: chore(phase-3): deploy v3 (32279ef)

---

## [P3 · c9] Phase 4 spec extended — the wireframe-fidelity decisions land in the plan

Slice C confirmed shipped first (the conditional must-ship dissolves). Phase 4 gains:
the table rules (amber ! as the affordance, holder admin-only, 32px targets, Tabler
glyphs, bidirectional sort closing the Phase 1 BACKLOG entry), the needs-review tab
with the only Review action, admin edit (wireframe-driven, not brief-required), the
`fixed:` clearing note as an ADR-0017 amendment, four sound events, desktop-only
scope. README documents the review-entry chain.
Commit: docs(phase-4): extend the wireframe-fidelity spec (397a0f8)

---

## Correction #5 — the deploy path was a landmine, and the AI client was a test-extra

Two production defects found by the live verification, neither visible to a 118-green
suite.

**What happened.** Attaching `GEMINI_API_KEY` made Railway redeploy from the branch
the service has tracked since Phase 0 — putting **v0 live**: no login route, the whole
inventory served without a session, ADR-0006 violated on the public URL until a
`railway up` (~4 minutes). The deploy docs said "push the branch; Railway builds",
which stopped being true the moment the phase branch changed names, and nobody noticed
because pushes *appeared* to deploy — they deployed nothing, and the old build kept
answering.

**Second defect, surfaced by the first's fix.** With v3 back, the auditor refused with
its own diagnosis: `No module named 'httpx'`. The Gemini client imported a library
that exists locally only as a test dependency — the suite mocks the client (ADR-0004),
so no test can ever import the real one. Replaced with stdlib `urllib`. ADR-0016's
refusal-with-a-reason is what made this a one-line read instead of a debugging
session: the 503 carried the ImportError verbatim.

**What I am taking from it.** "The suite is green" says nothing about the two layers
the suite deliberately never touches: the deploy trigger and the real provider call.
Both defects lived exactly there. The live smoke is not a formality — it is the only
test those layers have.

Commit: fix(phase-3): stdlib Gemini client, deploy docs match reality (bd5961d)

---

## [P3 · c11] The model default becomes the alias

`gemini-2.5-flash` answers 404 "no longer available to new users" on the deployment's
key — a fact only the live call could know. Default is now `gemini-flash-latest`;
a pin is one `GEMINI_MODEL` env var away. 118/118 (the suite mocks the client, as
designed — which is exactly why this had to be found live).
Commit: fix(phase-3): default to the gemini-flash-latest alias (189815c)

---

## [P3 · c12] The audit gets its own budget

The live audit refused with a read timeout: it was running on the search's 5-second
budget, and an audit prompt carrying the whole catalogue is not a search. 30s for the
audit route, 5s stays the search's (its degradation is designed and announced).
Refusing slowly is honest; refusing on a borrowed budget is just wrong. 118/118.
Commit: fix(phase-3): the audit gets its own timeout budget (d6868f4)

---

## [P3 · c13] The search budget meets the provider's actual latency

Live: every search degraded to keyword because gemini-flash-latest spends ~7.5s
thinking before emitting one small JSON object, and the thinking-off knob answers an
opaque 400. The spec's 5s was a guess; 12s is a measurement. The spec is amended in
place with the reason. 118/118.
Commit: fix(phase-3): search timeout meets measured provider latency (97b6967)

---

## [P3 · c14] Every document at v3 reality

README: AI layer in ✅ as shipped, two new ⚡ entries (12s search budget, railway-up
deploys) each with Why and Future, env table gains `GEMINI_API_KEY`/`GEMINI_MODEL` —
including the distinction the incident taught: the key is read per request so
*rotation* needs no redeploy, but *adding* the variable restarted the process, because
that changes the environment rather than a value in it. PROMPT_TRAIL Session 15
records the verification that amended the spec. DATA_AUDIT's "will show" became "did":
the live auditor flags id 10 and the `"Appel"` typo. CONTEXT gains *Finding*;
brainstorm's status note marks Phase 3 shipped. Brief check: README's four sections
present, ⚡ all carry Why+Future, AI_LOG covers Tooling / Data strategy / Prompt Trail
/ five Corrections, setup runs from a fresh clone with no new dependencies (the AI
client is stdlib). No gap left open.
Commit: docs(phase-3): bring every document to v3 reality (pending)

---

## [P3 · c15] Both gates answered — one blocker, already satisfied

`mvp-reviewer`: PASS WITH NOTES; its sole blocker (rerun `/security-review`, which had
only seen the docs+refactor state) was already met — the second run covered the full
diff at HEAD, zero findings. Filed per the blockers-only rule: the README's overstated
"add form rejects" chain claim corrected, post-import semantic-validation gap and the
flag-review race added to ⚠️ (same class as the last-admin race), the empty-filter
`semantic` label to BACKLOG. AI_LOG's remaining `(pending)` stays owed to final polish.
Commit: docs(phase-3): file the gate findings (pending)
