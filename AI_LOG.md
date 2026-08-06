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

