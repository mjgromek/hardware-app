# Prompt Trail

Grilling transcripts and architecture-shaping prompts, in the order they happened.
Append-only. Answers are preserved verbatim — the disagreements are the point.

---

## Session 1 — 2026-08-06 — Whole-project scope

**Skill:** `/grill-me` (mattpocock/skills) → delegates to `/grilling`
**Scope:** whole-project. Decisions everything else inherits, before any code exists.
**Status:** ✅ **Settled.** Round 1 answered in full; `brainstorm.md` rewritten to v2.

### What this session settled

| # | Decision | Outcome |
|---|---|---|
| 1 | Phase count vs. time budget | **Four phases, not six.** Grillings for Phase 2 and 3 only. 15–20 commits. AI log split into two formats. No ADR — it is a process decision, recorded in `brainstorm.md` v2 §0. |
| 2 | Deploy topology | **Single origin.** → ADR-0001 |
| 3 | Seed strategy / preserved contradictions | **Ingestion structural-only** → ADR-0002, **`needs_review` becomes a rentability guard** → ADR-0003 |
| 4 | Structured extraction, and the "AI-native" claim | **Filter object over prompt-stuffing**, justified by no-hallucination + testability rather than scale; "AI-native" dropped as an architectural claim. → ADR-0004 |
| 5 | Admin bootstrap + zero-admin invariant | **Env-var bootstrap, boot refusal, `409` guard.** → ADR-0005 |

Four questions were deferred at the time as depending on answers above. Three are
now resolved by v2; one remains open:

- ~~Where authorization is enforced~~ — still **open**, but unblocked: ADR-0001
  fixes it as a cookie, and v2 §7 defers the middleware-vs-dependency choice to
  Phase 1's first commit.
- ~~Which modules must be deep~~ — resolved by v2 §3: the state machine is the one
  load-bearing deep module, and the Phase 2 architecture pass exists to enforce it.
- ~~What not to build~~ — resolved by v2 §6 (Scope Control) and by MVP 4 and MVP 5
  ceasing to be phases.
- ~~LLM provider~~ — resolved as *deliberately deferred*: under ADR-0004 the schema
  does the load-bearing work, so any of the three candidates works (v2 §7).

---

### The invoking prompt (verbatim)

> I'm building "Hardware Hub" — an internal tool for Booksy employees to manage,
> rent and maintain company equipment. It's a recruitment task, ~4-5 hours, graded
> on engineering decisions and AI-tooling fluency more than feature count.
>
> Read brainstorm.md, CONTEXT.md and CLAUDE.md first.
>
> Grill me at WHOLE-PROJECT scope. I want the decisions everything else inherits
> settled before any code exists. Specifically:
>
> - Auth: JWT vs session cookie, where authorization is enforced, admin bootstrap
>   (no self-registration is allowed — admin creates all accounts)
> - The seed data is deliberately dirty (duplicate IDs, a future purchase date,
>   a status outside the enum, and two records marked Available whose notes
>   describe damage). My plan is to quarantine bad rows rather than drop them,
>   and to deliberately LEAVE the two contradictions in the DB so the AI auditor
>   can find them. Attack that plan.
> - What "AI-native" concretely means here, and whether structured filter
>   extraction beats embeddings at ~12 records
> - Module boundaries: what has to be a deep module, what can stay thin given
>   the time budget
> - What I should NOT build
>
> Rules for this session:
> - Do NOT go into individual MVP implementation detail — each MVP gets its own
>   grilling later. If I drift there, pull me back.
> - Push hardest where the time budget and the "rock-solid core over rushed
>   features" instruction conflict.
> - Where I give a weak answer, say so.

**Docs read before questioning:** `brainstorm.md`, `CONTEXT.md`, `CLAUDE.md`.

**Two corrections made on reading them:** `brainstorm.md §13` (Scope Control) exists,
so the `conductor` skill's reference to it is valid. And §14 requires the repo be
public from commit one, specifically to avoid a "made public" event late in the
history — which answered an earlier objection to creating the GitHub repo public.

---

## Round 1

### Q1 — Your process overhead exceeds your entire budget

Take your own numbers. Six `/grill-me` sessions at ~20 minutes each is **2 hours**.
Fifteen-to-25 commits, each with an `AI_LOG.md` entry in your §5 format — that entry
is nine lines of considered prose, call it 5 minutes honestly written — is
**100 minutes** at 20 commits. That's **3.5 hours of a 4–5 hour budget before a
single line of application code**, and your own log already records roughly an hour
lost to MCP debugging in Phase −1.

Then the plan wants six deploys, six review gates where you read every diff end to
end, three architecture passes, and eight maintained doc files.

This isn't a scheduling quibble — it's the central design flaw, and it's the exact
place you asked me to push hardest. "Rock-solid core over rushed features" is not in
tension with your time budget. Your *ceremony* is. The tests and the state machine
aren't what will blow the estimate; the six-phase gate ritual is.

Three honest resolutions:

**(a) Admit it's a 12–15h project** and spend it. Risk: a task scoped at 4–5 hours
submitted with 20 hours of scaffolding invites "does this person calibrate effort?"
— and your `.claude/` directory makes the investment visible in the diff.

**(b) Keep six phases, slash the process** — one grilling (this one), three-line log
entries, no architecture passes. Cheapest, but you delete the things actually being
graded.

**(c) Collapse to four phases, keep the rigor.** Phase 0 (foundation + data audit +
first deploy), MVP 1 (auth + admin + dashboard), MVP 2 (rental engine), MVP 3 (AI
layer). MVP 4 disappears as a phase — you already deploy from v0, so
"production-grade" is a checklist inside MVP 3's gate, not its own branch and gate.
MVP 5 becomes a single 45-minute polish commit, not a phase.

**Recommended:** (c). Four gates, not six. Two more grilling sessions (MVP 2 and
MVP 3) rather than five — Phase 0 and MVP 1 should be *settled by this session*.
And split the AI log: a three-line entry per routine commit, plus **four** long-form
entries in the §5 format reserved for genuine corrections. The brief asks for the
correction narrative; it does not ask for twenty of them. Twenty uniform nine-line
entries is also precisely the texture that reads as batch-written, which §5 says
you're trying to avoid.

**Answer — accepted, resolution (c):**

> - Workflow section: four phases, not six. Grillings only for Phase 2 and Phase 3.
> - AI log rule: two formats — three lines routine, long-form for corrections only,
>   three or four across the whole build.
> - Commit target: 15-20, roughly four per phase.

Recorded in `brainstorm.md` v2 §0 and §4. No ADR — this is a process decision, not
an architectural one. v2's header states the reasoning directly: *"The v1 plan had
roughly 3.5 hours of process overhead inside a 4–5 hour budget; that was the central
flaw and it is fixed here by collapsing phases, not by cutting rigor."*

MVP 4 (deployment) folds into Phase 3 as a gate checklist; MVP 5 becomes a single
polish commit on `main`.

---

### Q2 — Single origin or split origin? This decision is load-bearing and you haven't made it

§11 says "Railway, single repo, no serverless-filesystem problem." Single *repo* is
not single *origin*, and the difference decides your auth question, your CORS story,
and where the LLM key lives.

**Single origin:** FastAPI serves the built Vue bundle as static files; API and UI
share one host. No CORS at all. Cookies are same-site by definition. One deploy, one
URL, one env var set.

**Split origin:** Vercel frontend, Railway API. Two deploy pipelines, real CORS
config, and cookie auth now needs `SameSite=None; Secure` plus CSRF handling — or you
retreat to bearer tokens.

Note what single origin does to your §11 test list: `test_cors_rejects_unknown_origin`
becomes nearly vacuous, because there is no cross-origin path to reject. Shipping a
test that asserts a condition your architecture makes unreachable is worse than not
having it — a reviewer reads it as cargo cult.

**Recommended:** Single origin. FastAPI mounts `dist/` as static, SQLite on a Railway
persistent volume, one service. Replace the CORS test with an actual authorization
test. The cost is one build step wired into the deploy; the saving is an entire class
of configuration you now don't have to get right under time pressure.

**Answer — accepted in full.** → **ADR-0001**. `brainstorm.md` v2 §1 records it as
*"FastAPI mounts the built Vue `dist/` as static files. One service, one URL, one env
var set, SQLite on a Railway persistent volume"*, and carries the deletion of
`test_cors_rejects_unknown_origin` forward explicitly. v2 §5 (Stack) now states
single origin at the top of the plan rather than leaving it implied by "single repo".

---

### Q3 — Attacking the seed plan: your two "preserved contradictions" are rentable

You asked me to attack this, so here is the real hole. The Dell XPS has a swelling
battery and status `Available`. The MacBook Air has liquid-damage history and status
`Available`. In MVP 2 you build a rental engine whose entire selling point is that
guards make impossible states unreachable — and that engine will **cheerfully rent
out a laptop with a swelling battery**, because you deliberately preserved the dirt
to give the MVP 3 auditor something to find.

A reviewer can state that as: *you subordinated product safety to a demo moment.*
That's a hard sentence to answer in an interview.

Worse, there's a fork underneath it you haven't resolved. Either:

- **Ingestion could detect these** — "battery swelling", "liquid damage" are
  keyword-findable — and you chose not to, in which case you manufactured the problem
  your AI solves. That's the single most damaging reading available of an "AI-native"
  submission.
- **Ingestion genuinely can't** — semantic judgment is out of scope for a validation
  layer by design — in which case you need the auditor to catch at least one thing
  that has *no* keyword signature, or the whole AI layer is a regex with a language
  model's bill.

And separately: what does `needs_review` actually *do*? Right now it's a UI badge.
A flag that changes nothing is decoration.

**Recommended:** Draw the boundary explicitly and make it load-bearing: **ingestion
does structural validation only** (schema, enum, keys, dates); semantic contradiction
is out of its remit *by declared design*, and that boundary goes in ADR-0002. Then
make `needs_review` a **rentability guard** — a flagged item returns `409` with a
readable reason, using the same guard machinery as `Repair`. Now Phase 0's quarantine
work is product, not decoration, and the safety hole closes without deleting the demo:
the items stay in the DB, stay visible, stay unrentable, and the auditor still
explains *why* in language a keyword scan couldn't produce. Finally, prove the auditor
isn't a regex by requiring it to flag **id 10** (empty brand, null date, `Unknown`
status → "unidentifiable, needs physical audit") — a judgment with no keyword to match
— and say plainly in the README that a keyword scan would have caught the two obvious
ones.

**Answer — accepted, and split into two ADRs because the flaw had two halves.**
In the user's own words when commissioning the log entry:

> my v1 plan deliberately preserved two seed records with semantic contradictions —
> Dell XPS marked Available with "battery swelling" notes, MacBook Air marked
> Available with liquid-damage history — so the MVP 3 Inventory Auditor would have
> something to find. The whole-project grilling session caught that the MVP 2 rental
> engine, whose entire premise is that guards make impossible states unreachable,
> would have rented both out. The plan subordinated product safety to a demo moment.
>
> The correction: ADR-0002 declares ingestion structural-only so the boundary is
> principled rather than accidental, and ADR-0003 makes needs_review a rentability
> guard returning 409 — the items stay visible and stay unrentable.

→ **ADR-0002** and **ADR-0003**. Logged as long-form correction #1 in `AI_LOG.md`.

**Extended beyond the recommendation:** v2 §2 also quarantines and flags record 6
(future purchase date) and record 10 (empty brand, null date, off-enum status), so
`needs_review` now blocks rental on structural grounds too, not only semantic ones.
That is a wider net than was proposed — captured as a trade-off in ADR-0003.

---

### Q4 — Your reason for rejecting embeddings is the weak form of a strong argument

"With ~12 records, embeddings are theatre" is true but it's the *scale* argument, and
scale arguments evaporate the moment someone says "and at 12,000 records?" You'll have
no answer, because you'd have chosen differently, which means your decision was
contingent rather than principled.

At 12 records the sharper observation is that **retrieval is strictly dominated — the
entire catalogue fits in one prompt.** So the live question was never
embeddings-vs-filters. It was: why extract a structured filter instead of handing the
LLM the whole inventory and letting it answer?

That has two real answers, and they're both much stronger than scale:

1. **The LLM cannot hallucinate inventory.** It emits a filter object; SQLite returns
   rows. Every item a user sees provably exists in the database. Hand the model the
   catalogue and it can invent a fourteenth device, and you cannot prevent it.
2. **The AI layer becomes unit-testable.** `test_semantic_query_maps_to_filter_schema`
   asserts a deterministic object against a mocked LLM. "Model reads catalogue and
   returns prose" is testable only by snapshot, which is to say barely.

Both survive at 12,000 records. Scale becomes the footnote it should be.

Related, and I think you should concede it: is this **AI-native** or **AI-featured**?
Two features hanging off a CRUD app — a search box and a report — is the latter. The
brief's phrase is doing marketing work, and matching its vocabulary while your
architecture says otherwise is the kind of thing a technical reviewer notices.

**Recommended:** Rewrite the ADR around **no-hallucination + testability**, with scale
as a supporting note. And drop "AI-native" as a *claim* about the architecture —
instead let the engineering *around* the LLM be the thing that stands out:
schema-validated output, guaranteed-real results, graceful keyword fallback,
deterministic tests. That's a genuinely stronger position than the label, and it's
what "engineering decisions are expensive" is actually fishing for.

**Answer — accepted, with one correction to the recommendation.** → **ADR-0004**.

v2 §1 adopts the no-hallucination + testability justification and demotes scale to a
footnote: *"Scale is a footnote, not the argument. 'Only 12 records' collapses the
moment someone asks about 12,000."*

**Where the recommendation was overruled:** I proposed conceding the AI-native /
AI-featured distinction openly. v2 accepts the substance but rejects the delivery —
*"State that positively; don't editorialise about the brief's wording."* Dropping the
claim is right; narrating to a reviewer that their vocabulary was marketing is not.
The README states what the engineering does and says nothing about the phrase.

---

### Q5 — Admin bootstrap: no self-registration means admin #1 has to come from somewhere

You've stated the constraint but not the mechanism. The options are a seed script
reading `ADMIN_EMAIL`/`ADMIN_PASSWORD` from env, a hardcoded admin in the seed, or a
first-run setup flow. There's also an invariant hiding here that your §2.1 raises and
never settles: **can the system reach zero admins?** If an admin can delete or demote
themselves, the app has a permanently locked state reachable in two clicks — an
impossible-state bug in exactly the domain where you're claiming impossible states are
unreachable.

**Recommended:** Seed creates the admin from env vars; the app **refuses to boot in
production if `ADMIN_PASSWORD` is unset** (same shape as the existing
`test_prod_config_requires_secret_key`). Enforce "at least one admin exists" as a guard
in the same layer as the rental guards, returning `409` — it's the same class of
invariant and it should not live somewhere else. And publish a *separate* demo account
in the README rather than the real admin credentials, listed in the trade-offs table as
a deliberate demo affordance on a public deployment.

**Answer — accepted in full.** → **ADR-0005**. v2 §1 adds the reasoning for why the
invariant belongs with the rental guards rather than in user management: *"It is the
same class of invariant and must not live somewhere else."* Two tests carry it —
`test_app_refuses_to_boot_without_admin_password` (Phase 0) and
`test_cannot_remove_last_admin` (Phase 1), the latter covering demotion as well as
deletion, since either alone leaves the lockout reachable.

---

### Deferred to a later round

Not asked, because each depends on an answer still open above:

- **Where authorization is enforced** (middleware vs. per-route dependency) — blocks on
  Q2, since topology decides whether you're validating a cookie or a bearer token.
- **What must be a deep module vs. what stays thin** — blocks on Q1; the answer differs
  a lot between four phases and six.
- **What you should NOT build** — blocks on Q1 for the same reason.
- **LLM provider** (§14 open item) — blocks on Q4's shape.

---
