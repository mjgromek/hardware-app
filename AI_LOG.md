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
