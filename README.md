<div align="center">

# 🧰 Hardware Hub

### AI-assisted equipment management, rental, and maintenance platform

Internal tool for Booksy employees to manage company hardware safely — with role-based access, rental workflows, audit trails, AI-powered search, and inventory review.

<br>

[![Live Demo](https://img.shields.io/badge/Live_Demo-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)](https://booksy-hardware-hub.up.railway.app/)
[![Tests](https://img.shields.io/badge/Tests-198_passing-success?style=for-the-badge)](#-status)
[![AI Log](https://img.shields.io/badge/AI_Log-Development_Process-blueviolet?style=for-the-badge)](AI_LOG.md)
[![ADRs](https://img.shields.io/badge/Architecture-20_ADRs-blue?style=for-the-badge)](docs/adr/)

<br>

## 🛠️ Tools & Stack

<p>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vue_3-4FC08D?style=flat-square&logo=vuedotjs&logoColor=white" alt="Vue 3">
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white" alt="Railway">
  <img src="https://img.shields.io/badge/Gemini-8E75B2?style=flat-square&logo=googlegemini&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/Claude_Code-D97757?style=flat-square&logo=anthropic&logoColor=white" alt="Claude Code">
</p>

**Engineering workflow:** TDD · phase-based delivery · human review gates · custom subagents · MCP tooling

<br>

### 🔗 Live Demo

**[Open Hardware Hub](https://booksy-hardware-hub.up.railway.app/)**

|  | Demo access |
| :--- | :--- |
| **Email** | `demo@booksy.com` |
| **Password** | `hardware-hub-demo` |
| **Role** | `user` — read only |

<sub>Only admin-created accounts can sign in. There is no public read surface.</sub>

</div>

> [!NOTE]
> If the search bar shows **keyword mode**, the Gemini free-tier quota has been reached.  
> Semantic search falls back transparently, while the auditor returns `503` with a reason. This is intentional graceful degradation defined in ADR-0016.

---

## 🧭 How this was built

Five phases. Each one is a branch, a red test commit, a green commit, a deploy, and a
review gate before merging. Every phase below lists what shipped, which tools drove it,
and what went wrong.

The agent pipeline is the point of the structure: **whoever writes the tests never
writes the code.** `test-author` can only touch `tests/`, the implementer can only touch
`app/`, and the review agents have no write access at all. Without that split, one
context writes a test and then quietly softens it to pass.

---

### 🧱 Phase 0 · Foundation and the data audit

`v0-foundation`

The seed data is deliberately dirty. Handling it correctly was the first decision, not
the last.

**Shipped**

- Quarantine ingestion: bad rows are recorded with a reason, never dropped
- SQLite persistence, caller-owned transactions
- First deploy, so the pipeline was proven before there was anything to lose

**Tools** · `/grill-me` to settle the architecture · `test-author` agent for the red
pass · `/tdd` for green · GitHub MCP, Railway MCP

**Decisions** · [ADR-0002](docs/adr/0002-ingestion-is-structural-only.md): ingestion
validates _structure_ only. A date with one legal reading parses. A misspelled brand is
judgement, and judgement belongs to the AI layer and a human, not to a validator.

**What went wrong** · The repo sat in an iCloud-synced folder. Five unrelated-looking
bugs, one cause. Fixed by moving it. Recorded in `AI_LOG.md` at Phase 0, not as one of
the seven numbered corrections.

---

### 🔐 Phase 1 · Auth, admin, dashboard

`v1-admin`

**Shipped**

- Session cookie auth, `scrypt` with per-account salt
- `admin` and `user` roles, enforced per route
- Admin panel: add, delete, toggle Repair, manage accounts
- Sortable and filterable dashboard

**Tools** · `test-author` · `/tdd` · `frontend-design` skill for the UI ·
`/security-review` before the gate · `mvp-reviewer` agent

**Decisions** · [ADR-0006](docs/adr/0006-no-public-read-surface.md): every data route
needs a session. Found because `/api/hardware` was serving maintenance notes to anyone
with the URL.

**What went wrong** · `/security-review` found a full admin takeover. SQLite recycles
row ids, sessions named the row id, so a deleted admin's cookie could revive as a new
account. **91 passing tests did not see it.** Fixed with a surrogate session token and
soft-deleted accounts ([ADR-0013](docs/adr/0013-accounts-are-soft-deleted.md)).
`AI_LOG.md` P2 · c9.

---

### 🔄 Phase 2 · The rental engine

`v2-rental`

**Shipped**

- Rent, return, and admin force-return
- Guards: Repair, already rented, wrong renter, needs review, last admin
- Audit trail, one row per admin override, with a mandatory reason
- Needs-review queue with a release action

**Tools** · `/grill-me` first, this phase was not pre-settled · `test-author` · `/tdd` ·
`architecture-scout` agent · `mvp-reviewer`

**Decisions** ·
[ADR-0008](docs/adr/0008-atomic-claim-and-refusal-vocabulary.md): the claim is one
conditional `UPDATE` whose rowcount _is_ the decision. A guard that reads then decides
cannot win a race. ·
[ADR-0010](docs/adr/0010-audit-events.md): the transition writes its own audit row, in
the same transaction, so no caller can override silently.

**What went wrong** · The first implementation deadlocked under six concurrent renters:
it read the item, then tried to upgrade the lock. Inverting it, claim first and read only
to explain a failure, was what ADR-0008 had already prescribed. The code disagreed with
its own ADR.

---

### 🤖 Phase 3 · The AI layer

`v3-ai`

**Shipped**

- Semantic search: natural language, schema-validated filter object, SQLite returns rows
- Inventory Auditor: closed finding kinds, proposes, never acts
- Announced degradation: every response is labelled `semantic` or `keyword`

**Tools** · `/grill-me` on Fable 5 · `test-author` · `/tdd` · `/security-review` ·
`mvp-reviewer` · Gemini Flash as the model

**Decisions** ·
[ADR-0004](docs/adr/0004-structured-filter-extraction.md): the model emits a filter, not
an answer. It cannot hallucinate inventory, and the layer is unit testable against a
mocked model. Scale is a footnote, not the argument. ·
[ADR-0015](docs/adr/0015-no-restricted-field-predicates.md): the filter has no predicate
over `notes` for anyone. Otherwise result-set membership becomes an oracle: a user learns
the Dell XPS has battery notes by watching it match. ·
[ADR-0014](docs/adr/0014-the-auditor-proposes-never-disposes.md): the auditor proposes and never
disposes. A model that writes state can be argued into writing state.

**What went wrong** · The live URL was found serving a Phase 0 build with no auth,
leaking the notes ADR-0006 exists to protect. A human found it by opening the URL.
Nothing was watching. `AI_LOG.md` Correction 6, and `scripts/probe.sh` plus a scheduled
GitHub workflow now watch it every 30 minutes.

---

### 🎨 Phase 4 · Wireframe fidelity, elective

`v4-ui`

Beyond the brief. The wireframes were supplied, and a close copy is checkable in a way
that "looks fine" is not.

**Shipped**

- Wireframe-fidelity table, uniform controls, fixed column widths
- Dark mode, opt-in and persisted, light by default so a reviewer sees the wireframe
- Return with an issue: "anything wrong with it?", and a reported problem holds the item
- Two-outcome review: an admin confirms the fault and sends it to Repair, or releases it
  with a `fixed:` note. A review concludes, it does not only absolve
- Seven notification sounds, six as one family plus a distinct ask voice
- Measured WCAG contrast for every colour pair, both themes:
  [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md)

**Tools** · `frontend-design` skill against the wireframes · `test-author` · `/tdd` ·
Chrome MCP for live visual verification · `mvp-reviewer`

**Decisions** · [ADR-0020](docs/adr/0020-the-returner-may-flag-what-they-handled.md): a returner may raise a
flag the auditor may not. The auditor reasons over stored text, the returner handled the
equipment. This closes the loop seed record 11 implied: _"returned by user with liquid
damage"_ was an event the app previously could not have produced.

**What went wrong** · Four silent `str.replace` patches wrote nothing and exited zero.
Two features were reported as built and did not exist. `CLAUDE.md` now bans scripted
patching in favour of an editor that fails loudly. `AI_LOG.md` Correction 5.

---

### 🔎 Final · Grilling my own submission

Ran `/grill-me` on Fable 5 against the finished repo, as a hostile interviewer.

It found a real defect in **ADR-0002's own showpiece**. The date parser tried ISO then
day-first, so `"05-04-2023"` silently became 5 April. A guess about intent, in the
function used to argue that ingestion never guesses. The boundary held only because the
seed happened to contain an unambiguous date.

Fixed the same day: a date parses only when it has exactly one legal reading. Anything
else quarantines with both candidates named.

The old suite had **pinned the guess as a feature**, with a comment explaining it. That
is why it survived four phases and two security reviews.

---

## 📊 Status

### ✅ Fully implemented

Quarantine ingestion, nothing deleted · session auth with roles, enforced per route ·
admin panel with full CRUD and account management · sortable, filterable dashboard ·
rental engine with an atomic claim and five guards · audit trail on every override ·
needs-review queue with two-outcome release · return with an issue · semantic search with
announced fallback · Inventory Auditor · field-level authorization · company-domain
accounts · dark mode · measured accessibility · demo reset route · health endpoint ·
deployed smoke check · **198 tests**

### ⚡ Shortcuts and hacks

**Demo credentials published on a public instance**
Why: a reviewer is signed in within ten seconds. `/security-review` cut the role from
admin to user, because read access is what a reviewer needs and delete rights are what an
attacker wants.
Future: per-reviewer invite links.

**AI runs on Gemini's free tier, which rate-limits**
Why: a paid tier buys nothing the design does not already handle. The fallback is
announced and tested, and replies are cached.
Future: a paid tier behind the same seam. The cache and the label carry over unchanged.

**Seeds itself on boot when the database is empty**
Why: Railway offers no exec, no SSH, and `preDeployCommand` silently did not run. The
emptiness guard makes it safe: once rentals exist the table is never empty.
Future: a migration step. Boot logic should not write data.

**Sign out is client-side only**
Why: stateless sessions were the cheap correct thing for one process. Deleting an account
does revoke its sessions.
Future: a logout route and session expiry.

**A soft-deleted email is reserved permanently**
Why: the audit trail names actors by email, and reuse rebuilds the ambiguity the soft
delete removed.
Future: an archived-identity table.

**119 commits against a 15 to 20 target**
Why: TDD is two commits per slice by construction, and four incidents each needed their
own cycle. Every commit carries its log entry because a pre-commit hook refuses it
otherwise.
Future: nothing. Rewriting history to hit a number destroys what the brief asked to see.

**The wireframes are not committed**
Why: Booksy's material, marked confidential, and this repo is public.
Future: in a private repo they would sit beside the justification doc.

### ⚠️ Partial and missing

- No CI, and no frontend tests. The oldest gap and the one that aged worst
- No logout, session expiry or login throttling
- The last-admin guard is not race-safe. Reproduced, documented, deliberately not fixed:
  the trigger is concurrent demotions on a two-admin tool. The neighbouring case, a rent
  racing an account deletion, _was_ real and _is_ fixed
- Post-import data is validated structurally, not semantically. A manually added item
  with a 2027 date is caught by nothing
- No edit history beyond one audit row per override

### 🔮 Next steps

1. **CI and vitest.** Both suites in a workflow, plus tests over the table's keyboard
   behaviour and the client's `401` handling
2. **Logout and session expiry.** The other half of the session story

---

## 🧪 The AI development log

[`AI_LOG.md`](AI_LOG.md) has an entry for every commit, enforced by a pre-commit hook,
and seven long-form corrections indexed at the top.

**Tooling** · Claude Code with Opus and Fable 5 · `mattpocock/skills` for `/grill-me`,
`/tdd`, `/improve-codebase-architecture` · Anthropic's `frontend-design` ·
four custom subagents in [`.claude/agents/`](.claude/agents/) · GitHub, Railway, Context7
and Chrome MCP servers · Gemini Flash for the product's AI layer

**Data strategy** · [`docs/DATA_AUDIT.md`](docs/DATA_AUDIT.md). Ten defect classes,
what ingestion did with each, and `test_importer_reproduces_documented_audit`, which
makes the document falsifiable rather than descriptive.

**Prompt trail** · [`docs/PROMPT_TRAIL.md`](docs/PROMPT_TRAIL.md). Twenty sessions,
indexed by which ADR each produced. Verbatim where kept, marked _reconstructed_ where not.

**The correction** · Seven of them, plus the ADR-0013 takeover written up in place at
P2 · c9, which is the one worth reading first: a
recycled row id produced full admin takeover, reachable in three requests, under 91
passing tests. Found by `/security-review`, not by TDD, because **TDD verifies the
behaviours you thought to demand.** What changed structurally: any test that creates an
entity now gets a sibling that destroys it and replays every consumer of its identity.

---

## 💻 Running it

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cd frontend && npm install && npm run build && cd ..

.venv/bin/python -m scripts.seed
.venv/bin/python -m uvicorn app.main:create_app --factory --reload
```

Then http://127.0.0.1:8000. Development mode is permissive by default; production is
strict and refuses to boot without `SECRET_KEY` and `ADMIN_PASSWORD`.

**Tests**

```bash
cd frontend && npm run build && cd ..   # one test asserts against the real bundle
.venv/bin/python -m pytest
```

**The commit gate**, which a fresh clone needs:

```bash
git config core.hooksPath hooks
```

`hooks/pre-commit` refuses any commit that does not stage `AI_LOG.md`. It exists because
the convention held only as long as somebody remembered it: an audit at the Phase 1 gate
found 24 commits against 22 entries.

---

## ⏱️ On the time

About 10 hours against the brief's 4 to 5. The three pillars, v0 to v3, took roughly 7.
v4 is elective. Both figures are checkable from the phase tags.

Five of those hours produced no code anyone will read: a repo inside an iCloud folder,
MCP setup that `gh` and a dashboard replaced, agent briefs loose enough to produce 18
tests where 9 were asked for, scripted patches that silently did nothing, and UI
decisions reversed three times.

The arithmetic is uncomfortable and worth stating: the pillars cost four or five hours of
real engineering, so the timebox was hittable. The documentation is not where the surplus
went, because it cost almost nothing marginal. It was written in the moment, three lines
per commit, ADRs at decision time, never reconstructed. What the wasted hours bought is
the corrections log, and that is the difference between waste and tuition.

An over-engineering audit run after completion found the production code **not**
over-built for the task: dependencies at the floor, thin modules, the heavier machinery
traceable to specific incidents. What it flagged as excess was the sound system and the
documentation ratio, both of which this brief happens to grade. See `BACKLOG.md`.

---

## 📚 Documentation

| File                                                                 | What it is                                                                             |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [`docs/adr/`](docs/adr/)                                             | 20 architectural decisions. Six carry dated amendments, appended rather than rewritten |
| [`AI_LOG.md`](AI_LOG.md)                                             | Every commit, and seven corrections. Index at the top                                  |
| [`docs/PROMPT_TRAIL.md`](docs/PROMPT_TRAIL.md)                       | 20 sessions, mapped to the decisions they produced                                     |
| [`docs/DATA_AUDIT.md`](docs/DATA_AUDIT.md)                           | The seed's defects and what ingestion did about each                                   |
| [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md)                     | Measured contrast, both themes, generated from the stylesheet                          |
| [`docs/WIREFRAME_JUSTIFICATION.md`](docs/WIREFRAME_JUSTIFICATION.md) | Every UI deviation, in prose. The images stay uncommitted                              |
| [`BACKLOG.md`](BACKLOG.md)                                           | What is owed, each with the condition that makes it urgent                             |
| [`CONTEXT.md`](CONTEXT.md)                                           | The domain language                                                                    |
| [`CLAUDE.md`](CLAUDE.md)                                             | The rules every session reads                                                          |
