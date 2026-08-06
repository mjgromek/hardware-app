# Prompt Trail

The prompts that shaped the architecture and design, in the order they happened.
Append-only.

Two parts, because the material differs. **Part I** is one grilling session, transcribed
verbatim — the disagreements are the point, so the answers are preserved as given.
**Part II** is the architecture-shaping prompts from ordinary build sessions, each marked
*verbatim* or *reconstructed* depending on whether the wording survived. Every entry names
the commit and the ADR it produced, so a claim here can be checked against the code.

---

# Part I — Grilling 1

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

---

# Part II — Architecture-shaping prompts after grilling 1

Session 1 above is a full verbatim transcript, because it was one long interactive
grilling. Everything below happened in ordinary build sessions, so the record has two
different qualities and this file labels which is which:

- **Verbatim** — the prompt as typed, recovered from the session transcript.
- **Reconstructed** — the prompt is gone; what survives is the decision, in `AI_LOG.md`
  and the ADRs. The entry states what was asked for in substance and marks itself
  reconstructed. It is evidence of the decision, not of the wording.

Backfilled in one pass at Phase 1's review gate, having noticed this file had not been
touched since commit 3 of 24 while five architectural decisions had been taken since.
That gap is itself worth recording: the ADRs kept up and the prompt trail did not,
because ADRs are a non-negotiable in `CLAUDE.md` and this file was listed only as
"after every grilling" — and no grilling happened in Phases 0 or 1 by design.

---

## Session 2 — Phase 0 build — *reconstructed*

**Status:** ✅ settled. **Source:** `AI_LOG.md` [P0 · c1]–[P0 · c12], Correction #2.

Three architectural decisions came out of this phase that were not in any grilling.

**The findings-discipline rule.** *(Reconstructed — the prompt was a question about what
a reviewer would see if the budget ran out at that moment.)* The agent pipeline had been
surfacing real spec gaps at a rate that turned every one into work: a persistence layer
with caller-owned transactions, replace semantics specified rather than inferred, 26
tests including a mutation-verified check that `persist` does not commit — and zero
visible product. The answer became a standing rule in `CLAUDE.md`: non-blocking findings
go to `BACKLOG.md` and work continues; only something that makes the current work *wrong*
interrupts. → `AI_LOG.md` Correction #2, commit `29779c2`.

**Seed-on-boot-if-empty.** *(Reconstructed — driven by the deploy failing three ways.)*
Railway's API exposes no exec or SSH, `preDeployCommand` silently did not execute across
two deploys, and `railway ssh` needed an SSH key the machine did not have. With no way to
run `python -m scripts.seed` once against the mounted volume, seeding moved into
`create_app`, guarded by emptiness. Recorded as a deploy shim rather than a migration
strategy, because boot logic that writes data couples "the process started" to "the data
changed". → `BACKLOG.md`, commit `74c38f6`.

**A passing log assertion proves nothing about visibility.** *(Reconstructed.)* The
boot-seed log line was emitted, asserted, and never appeared in production: under uvicorn
the root logger has no handler, and `caplog` captures propagated records regardless. Found
by reading deploy logs for a line that should have been there. → commit `3efe885`.

---

## Session 3 — Wireframes are confidential and this repo is public — *verbatim*

**Status:** ✅ settled. **Commits:** `36ec0b4`, `3121790`.

> Add docs/wireframes/ to .gitignore — the wireframes are Booksy's material, the brief
> marks it confidential, and this repo is public.
>
> Create docs/WIREFRAME_JUSTIFICATION.md with a header explaining they're kept locally
> and deliberately not committed, and that deviations are described in prose so the
> document stands alone without them.

**Why this is architectural rather than housekeeping.** It fixes the form of every UI
justification for the rest of the build: each deviation has to describe what the original
showed *before* saying what was built, because the reader cannot open the image. The
thirteen Phase 1 entries are all written to that constraint.

Checked before anything was staged that the images had never been committed
(`git log --all -- docs/wireframes` was empty), so no history rewrite was needed.

A follow-up in the same session aligned the README's status headings with the brief's
four (`✅ Fully Implemented`, `⚡ Shortcuts & Hacks`, `⚠️ Partial / Missing`,
`🔮 Next Steps`), which forced a distinction that had been blurred: what works but cost
something is a shortcut, what does not exist is missing. It also surfaced a stale test
count — the README said 28 where collection reported 30.

---

## Session 4 — Phase 1 red, and the prompt that exposed a Phase 0 defect — *verbatim*

**Status:** ✅ settled → **ADR-0006**. **Commit:** `0b0bd7e`.

> Use the test-author agent for Phase 1.
>
> Input: brainstorm.md §3 Phase 1 test list, plus ADR-0001, 0003, 0005.
>
> Write the nine Phase 1 tests as failing tests. Tests only — never app/ or frontend/.
>
> Scope: login, session cookie (same-site, free under single origin), admin/user roles,
> admin CRUD on hardware, admin account creation, the last-admin guard, and dashboard
> sort/filter.
>
> Per CLAUDE.md findings discipline: non-blocking observations go to BACKLOG.md, not to
> me. Only interrupt if something makes the current work wrong.

**What it produced that nobody asked for.** `test-author` wrote the nine, plus a tenth
pinning the session cookie's `HttpOnly` and `SameSite` attributes — §3 names the cookie
as scope and no named test touched it, and ADR-0001 making `SameSite` *free* is not the
same as it being *set*. It also filed a question rather than deciding it: its tests read
`/api/hardware` anonymously because Phase 0's green tests did, and reversing that would
turn three passing tests red, which is not a test author's call.

The answer, in the next prompt:

> Settle the open question: GET /api/hardware requires a session. The brief says only
> admin-created users can access the Hub, so an unauthenticated inventory endpoint
> contradicts it.
>
> Use the test-author agent to update the two Phase 0 tests that assumed no auth. This is
> a spec change, not test-weakening — record it in BACKLOG.md as resolved and note it in
> the AI_LOG entry.

It was three Phase 0 tests, not two. → **ADR-0006**, written in a later prompt in the
same session with an explicit instruction about what the argument had to be:

> Lead with the concrete reason, not the brief's wording: /api/hardware was serving notes
> and history to anyone with the URL — the Dell XPS "battery swelling" note and the
> MacBook's liquid-damage history, internal maintenance records, public on the internet.
> The brief's "only admin-created users can access the Hub" is the supporting citation,
> not the argument.

**The decision worth reading twice:** the endpoint was wrong when it shipped in Phase 0,
not newly wrong in Phase 1. ADR-0002 keeps that free text in the database as the Phase 3
auditor's raw material, which makes the exposure worse rather than incidental — the fields
are candid *by design*.

Two sub-decisions inside the same change: the boot-seed pair moved off HTTP to
`app.storage` rather than growing a login, since their subject is what boot did to the
table and not who may read it; and `GET /` stays public, pinned by
`test_serves_built_bundle_at_root`, or nobody can reach the login page.

---

## Session 5 — Phase 1 green, and the enforcement point — *verbatim*

**Status:** ✅ settled. **Commit:** `180329c`. Closes v2 §7's last open question.

> /tdd — Phase 1 green. Login first, then re-run and confirm all eleven fail on their own
> assertions, not in the fixture. Contract is tests/conftest.py:22. Don't edit tests/.

**Where authorization is enforced — the question deferred from grilling 1 Round 1.**
Answer: **per-route dependencies, not middleware.** The argument is not preference. A
global "refuse without a session" middleware sees the static mount too, so it takes `GET
/` down with it — and `test_serves_built_bundle_at_root` fetches `/` unauthenticated and
is green. The wrong shape fails a passing test instead of shipping. A dependency also puts
the requirement in the signature of the route it protects.

**The guard layer.** ADR-0005 says the zero-admin invariant lives in the same layer as
the rental guards, so it went in `app/guards.py` rather than a handler, with one
`_enforce` helper mapping `GuardViolation` to `409` with the reason intact. Phase 2's rent
and return now find a layer rather than a precedent of inline `if` statements.

**Credential path, standard library only** — `hashlib.scrypt` with a per-account salt and
an HMAC-signed cookie, no new dependency, matching `app/config.py`'s existing stance. The
digest has no field on `domain.Account`, so no route can echo one.

The instruction to confirm all eleven fail *on their own assertions* is the part that
earned its keep: seven had been failing in fixture setup behind a login that did not
exist, which is a different fact from failing on their subject.

---

## Session 6 — Pace, and pruning the working documents — *verbatim*

**Status:** ✅ settled. **Commit:** `d26270f`.

`CLAUDE.md`, `CONTEXT.md` and the three agent briefs were replaced with shorter versions,
adding explicit pace rules — report in five lines, make reversible decisions yourself,
stop only for security, data loss, or a contradiction with an ADR. Then:

> Prune BACKLOG.md. Delete outright: […] Keep only what is still true and still
> unaddressed.

**The rule this established:** backlog entries are deleted when done, not annotated. The
record of *why* something changed belongs in `AI_LOG.md` and `docs/adr/`; a backlog that
carries its own history stops being a list of what is owed. Four entries went, plus three
more the same audit found had been closed by the green commit.

---

## Session 7 — The Phase 1 UI, and two routes the spec never had — *verbatim*

**Status:** ✅ settled. **Commit:** `1dc0921`.

> Build the Phase 1 Vue UI. Wireframes in docs/wireframes/ as reference.
>
> Screens: login, dashboard (sortable/filterable table), admin panel (add/delete
> hardware, toggle Repair, create accounts), needs_review queue.
>
> Constraints: internal tool, the dense table is the primary surface, clarity over
> expressiveness, status legible at a glance across Available / In Use / Repair /
> needs_review. Focus states and keyboard nav on the table. 401 shows the login screen.
>
> Deviations from the wireframes go in docs/WIREFRAME_JUSTIFICATION.md as you make them.

**Two endpoints the wireframes required and §3 never specified**, both written test-first
in new files rather than by touching `test-author`'s green ones:

- `POST /api/hardware` — the wireframe's "Add New Device" button had nothing behind it.
- `GET /api/session` — the cookie is `HttpOnly`, so a reloaded page knows it has a
  session but not whose. The alternative was probing `/api/users` for a `403` and reading
  an authorization failure as data, which makes a genuine permissions bug and a plain
  `user` account indistinguishable.

**The design decision inside the constraint "status legible at a glance across Available
/ In Use / Repair / needs_review".** Those four are not one axis. A flagged item still has
a status — both flagged seed rows are `Available` — so `needs_review` cannot be a fourth
chip in the status cell. It takes its own column plus an amber edge marker on the row,
which is what makes it scannable down a dense table without reading every line. Thirteen
deviations recorded; the load-bearing ones are the status labels keeping the enum's words,
and the login screen having no client-side `@booksy.com` rule (it would lock out
`ADMIN_EMAIL`, and it leaks the domain fact the API refuses to confirm).

**A correction in this session, and it was the assistant's.** Verifying the live
deployment, `DELETE /api/users/1` was sent at production expecting the ADR-0005 guard to
refuse it. It did not refuse — correctly, a second admin had just been created for the
demo account — and the deployment's real bootstrap admin was deleted. Restored
immediately; inventory untouched. The lesson recorded was not "be careful with DELETE" but
that a *destructive* probe was run to observe a *refusal*, against production, when
`test_cannot_remove_last_admin` already proved that behaviour locally.

---

## Session 8 — Security review triage — *verbatim*

**Status:** ✅ settled. **Commit:** `332b87a`.

> Triage the /security-review findings. Fix only what is genuinely exploitable on a public
> deployment with published demo credentials. Everything else goes to the README ⚠️
> Partial section with a one-line reason, not to BACKLOG.

`/security-review` raised two code findings and both filtered out as false positives: the
dev `SECRET_KEY` fallback (the live service sets `ENVIRONMENT=production`, provable from
outside because the session cookie returns `Secure` and only that branch sets the flag),
and the `notes`/`history` exposure (this branch *narrowed* it from anonymous to
authenticated; what remains is maintenance prose about laptops).

**The genuinely exploitable thing was what the review flagged as outside its own scope:**
the README published an **admin** credential on a public instance, so any reader had
delete rights over the inventory and the account list. `demo@booksy.com` is now `user`;
all five admin routes answer `403` to it.

This settles *inside* ADR-0005 rather than against it — the ADR requires published demo
credentials and never said they had to be admin. The cost is recorded: the admin panel is
no longer reachable with the published credential.

**The triage rule this established:** accepted-not-fixed findings go to the README's
`⚠️ Partial / Missing` section with the reason, not to `BACKLOG.md`. A reviewer reads the
README, and "we knew and chose not to" belongs where the claim is made.

---

## Session 9 — 2026-08-06 — Grilling 2, Phase 2 scope — *verbatim*

**Skill:** `/grill-me` → `/grilling` **Scope:** whole-phase, Phase 2 only.
**Status:** ✅ **Settled in two rounds.** Round 3 was cut deliberately — see the closing
instruction. Produced ADR-0007–0012, an amendment to ADR-0003, and `docs/specs/phase-2.md`.

### The invoking prompt (verbatim)

> Phase 2, the rental engine. Read brainstorm.md §3 Phase 2, CONTEXT.md, ADR-0003 and
> ADR-0005.
>
> Push hardest on: two users racing for the same item; whether an admin flipping to Repair
> kills an active rental; who may return an item (renter, admin, both); and how
> needs_review gets cleared — Phase 2 now owns that.
>
> Whole-phase scope only. Don't drift into Phase 3.

### Facts established before Round 1 (looked up, not asked)

- **Seed id 7 is a live rental with no account behind it** — `Sony WH-1000XM4`, `In Use`,
  `assignedTo: "j.doe@booksy.com"`. No such account exists; Phase 1 creates only
  `ADMIN_EMAIL` and the demo user.
- **Phase 1 already shipped the impossible state.** `PATCH /api/hardware/{id}` →
  `set_status` has no guard, so an admin can flip item 7 from `In Use` to `Repair` today.
  `CONTEXT.md` lists "a rented item in `Repair`" as an impossible state. So the Repair
  question is a retrofit onto a live endpoint, not a greenfield choice.

---

### Round 1

**Q1 — Where does rental truth live?** `hardware.status` + `assigned_to` as source of
truth with a `rentals` log; or `rentals` as truth with `status` derived; or `status`
computed on read.
→ **Recommended (a) + a partial unique index on `rentals(item_id) WHERE end IS NULL`.**
Computed status is cleaner in theory and wrong here — `status` is what the seed ships, the
dashboard filters on, and 55 tests assert against. The index makes "two active rentals on
one item" unreachable at the database level rather than by a guard that has to remember.
**Answer — accepted.**

**Q2 — How is the renter identified?** FK to `users.id`; email snapshot; or both.
→ **Recommended both.** A bare FK cannot represent seed id 7; `ON DELETE CASCADE` on
history means deleting an employee erases the record that they held the laptop, which is
the one fact an audit wants. A bare string cannot answer "is this the signed-in user"
without comparing on an identity, which is how wrong-user guards break subtly.
**Answer — accepted.**

**Q3 — Does an admin flipping to `Repair` kill an active rental?** Refuse `409`;
force-return; or allow coexistence.
→ **Recommended refuse, plus a separate explicit force-return.** Physical reality argues
for force-return — a swelling battery should be marked `Repair` whether or not someone is
holding it — but silent state changes to somebody else's rental are how audit trails
become fiction. Refusing makes the admin take one deliberate extra action, and that action
is the record. **Changes the shipped `PATCH /api/hardware/{id}`.**
**Answer — accepted.**

**Q4 — Who may return an item?** Renter only; renter or admin as the same verb; or renter
returns and admin *force-returns* as a distinct audited verb.
→ **Recommended the third.** Renter-only strands every item whose holder leaves the
company, and this system has no logout let alone offboarding. Folding admin into the same
verb makes `test_cannot_return_someone_elses_rental` quietly weaker than its name — it
would pass for a `user` and be meaningless for an admin, and reviewers read the name.
**Answer — accepted.**

**Q5 — Two users race — where does atomicity live?** A guard that reads state then decides
cannot win a race, because the read and the write are separate.
→ **Recommended: guards pre-check for readable errors; the actual claim is an
`UPDATE … WHERE status='Available'` whose zero rowcount means "you lost".** The honest part
is admitting the guard layer is *not* the sole decision point for this one transition,
because atomicity cannot live in a pre-check. `BEGIN IMMEDIATE` would keep the story tidier
and is more machinery for one transition, and survives a second replica no better.
**Answer — accepted.** *(Placement revised in Round 2, Q9.)*

**Q6 — How does `needs_review` get cleared, and what is recorded?** Reuse
`hardware_quarantine`; a new table; or columns on `hardware`. And: is a reason mandatory?
→ **Recommended a new table with a mandatory free-text reason.** Reusing
`hardware_quarantine` is wrong because `persist` has replace semantics — a reseed truncates
it, so an audit trail lives there only until the next documented seed run. Columns on
`hardware` cannot hold two review cycles. The reason is the whole point: "somebody
inspected this and it is fit to issue" is the claim a later incident interrogates.
**Answer — accepted, with an amendment that also settled Round 3's last question:**

> not a review_decisions table — one audit_events table serving force-return, clear-flag,
> and any future admin override. Same shape (actor, action, item, reason, timestamp), and
> the two verbs you just designed in Q4 and Q6 are the same kind of event: an admin doing
> something to a rental or an item that the ordinary user could not, with a reason
> attached. Two tables for one concept is the shallow-module smell architecture-scout will
> flag next phase anyway.

**Q7 — What happens to seed id 7?** Backfill an account; a rental row with a `NULL`
account and the email snapshot; or release it like id 2's orphan rental.
→ **Recommended the `NULL`-account rental.** Releasing it is what Phase 0 did to id 2 — but
id 2 was released *because it had no assignee at all*; id 7 names one, so releasing
destroys the only evidence of who holds the headphones and `docs/DATA_AUDIT.md` would need
a fourth divergence. Backfilling invents a passwordless account, a login-shaped hole
created for tidiness. **Answer — accepted.**

**Q8 — Is the UI in Phase 2's scope?** §3 lists no UI, but the wireframes' `Rent` buttons
and `My Rentals` were both deferred *from* Phase 1 in writing.
→ **Recommended engine + Rent/Return + My Rentals, and it is the first thing to cut.** A
rental engine no reviewer can operate is the failure mode `AI_LOG.md` Correction #2 already
burned this project once. **Answer — accepted.**

---

### Round 2

Two facts established first: **`PRAGMA foreign_keys = 0`**, so any declared FK is
documentation rather than a constraint; and **two existing routes destroy rental data
silently** — `persist` truncates `hardware` and is a *documented live operation*
(`railway run … python -m scripts.seed`), and `delete_item` lets an admin delete an item
that is `In Use`.

**Q9 — Where does the state machine live, and does it own the SQL?** `rentals.py` owning
transitions *and* their statements; `rentals.py` deciding and `storage.py` writing; or
extending `guards.py`.
→ **Recommended `rentals.py` owns both.** Splitting decision from write makes both modules
shallow — `storage.py` would hold a `WHERE status='Available'` encoding a rule it claims
not to know, and `rentals.py` would be a pass-through wrapper, the exact shape
`architecture-scout` is briefed to flag. **This revises my own Round 1 Q5 answer**, which
put the `UPDATE` in `storage.py` — the substance stands, the placement was wrong.
**Answer — accepted; amends ADR-0003 rather than getting its own ADR.**

**Q10 — `rentals` schema: one table or two, and who closed it?**
→ **Recommended one table, `ended_at` nullable, plus `closed_by_account_id`,
`closed_by_email`, `close_kind`.** Two tables turn every return into two writes with a
window where the rental is in neither or both, and the partial unique index already
provides what that reaches for. `close_kind` is what lets `My Rentals` say "recalled by an
admin" instead of showing the item silently gone. **Answer — accepted.**

**Q11 — `audit_events` shape, and does it get backfilled?**
→ **Recommended a closed action enum; no backfill; ordinary rent/return excluded.**
Retro-writing events for Phase 1 admin actions that were never observed would be
fabricating an audit trail, which is strictly worse than a gap — and the gap is
disclosable. Ordinary rent/return stay out because the amendment defines this table as
admin overrides; a user renting a laptop is the product working, and the `rentals` row is
its record. **Answer — accepted.**

**Q12 — What stops a reseed or an admin delete from orphaning rentals?**
→ **Recommended all three protections, and `persist` refusing is the one you cannot
skip.** `seed_if_empty` guards the *boot* path, but the README documents a manual reseed
against the live instance — the exact "restart destroys rentals" disaster the emptiness
guard prevents, reachable by the documented command instead of by a restart. The
`delete_item` guard checks *active* rentals only, so a returned item stays deletable with
its history intact. `foreign_keys` is unrelated to the locking pragmas `BACKLOG.md` warns
off and does not affect the isolation `test_persist_does_not_commit` pins.
**Answer — accepted.**

**Q13 — Clear-flag semantics.**
→ **Recommended clear regardless of status; `409` if not flagged; no re-flagging in Phase
2.** Status and the flag are orthogonal — the same reasoning behind the Phase 1 UI giving
`needs_review` its own column rather than a fourth chip. `409` on an unflagged item because
idempotency hides a UI bug *and* writes an audit row with a mandatory reason attached to a
non-event. **Answer — accepted.**

**Q14 — How distinguishable are the `409` reasons?**
→ **Recommended one reason per cause, with the race loser receiving the `In Use` reason.**
By the time the loser is told, "somebody else has it" is simply true — it is the current
state, not a race report, and a client rendering "another user claimed this microsecond
before you" leaks implementation detail as UX. Resolves the apparent tension in Q5.
**Answer — accepted.**

**Q15 — Who may see who holds an item?** Phase 2 turns `assigned_to` from seed residue into
live data about colleagues.
→ **Recommended renter identity visible to all signed-in users, `notes`/`history`/
`review_reason` restricted to admins.** Hiding the renter breaks the product — the point of
`In Use` on an internal tool is knowing who to ask — and it moves that conversation to
Slack where the tool cannot see it. Restricting the prose closes `/security-review`'s
open field-level finding as a side effect of serialisation work Phase 2 must touch anyway.
**Answer — accepted.**

---

### Round 3 — cut, deliberately

The frontier was not empty. Four questions remained: what
`test_rental_history_records_both_ends` asserts, which ADRs Phase 2 writes, the `My
Rentals` payload, and whether force-return needs its own named test. The instruction:

> Stop here — no round 3. Round 3's four questions get settled in /to-spec, not in another
> grilling round. Phase 2 is already wide.

Recorded because the grilling skill's own stopping condition is an empty frontier, and this
session stopped short of it on purpose. The four are specification detail rather than
architecture — none of them changes what the other decisions mean — and Phase 2 carrying
two shipped-route retrofits, a new module, two new tables and a UI is already the widest
phase in the project.


---

## Session 10 — 2026-08-06 — Agent-brief revision #2 — *verbatim*

**Status:** ✅ settled. **Commit:** `chore: tighten test-author brief for pace`.

Not a prompt to a model — an edit to `.claude/agents/test-author.md`, the file that
*becomes* the prompt every time that agent runs. It is in this trail because an agent brief
shapes what gets built as much as any instruction typed into a session, and it does so
invisibly and repeatedly. This is the second such revision, which is why it is worth a
numbered entry rather than a line in a commit message.

**The change:** one input file instead of four; *"write exactly the named list"* replacing
*"the named test list is your floor, not your ceiling"*; a hard cap of twelve tests;
mutation testing banned outright; a five-line report cap.

**The observation behind it:** 18 tests in Phase 0 and 11 in Phase 1 against a named list
of nine, at roughly twenty minutes a phase, on a brief that asks for three critical tests.
The output was good and the aggregate was wrong.

**Why it belongs in an architecture trail.** The first revision was the original agent
split itself — `test-author` may not touch `app/`, the implementer may not touch `tests/`
— recorded in `AI_LOG.md` [Phase −1 · commit 1] as the thing that makes TDD structurally
enforced rather than aspirational. That decision shaped every phase since. This one shapes
every phase remaining, in the opposite direction: the first bought rigor at the cost of
speed, this one sells some of it back. Both are architecture. Neither is code.

The full reasoning, including why it is the same mistake as Correction #2, is in
`AI_LOG.md` Correction #3.


---

## Session 11 — 2026-08-06 — Model assignment as an architectural choice — *verbatim*

**Status:** ✅ settled. Not a prompt and not a brief edit — a change to *which model runs
which role*, which belongs here for the same reason Session 10 does: it changes what gets
produced, invisibly and on every run.

**The change:** `mvp-reviewer` runs on Fable 5, and grilling sessions use Fable 5 from
here. Implementation stays where it is.

**The reason:** reasoning depth pays where a miss is silent. Implementation is fenced by a
spec and a red test — a weaker model that reaches the same green has produced the same
result, and the test says so immediately. Adversarial self-review and grilling have no
such fence. Nothing fails when a reviewer overlooks a finding or a grilling asks the
comfortable question, and this project has twice been saved at exactly those two points:
grilling 1 caught a rental engine that would have issued a laptop with a swelling battery,
and `mvp-reviewer` caught a session signature that 47 passing tests did not defend.

**Why it is architecture rather than configuration:** the review gate and the grilling are
the two places where the project's direction can still change cheaply. Spending the
deepest model there and not on the loop is the same trade as the agent-brief revision in
Session 10 — buying rigor where it compounds and paying for it where it does not.


---

## Session 12 — 2026-08-06 — `/security-review` at the Phase 2 gate → ADR-0013 — *reconstructed*

**Status:** ✅ settled → **ADR-0013**. **Commit:** `5d33b44`. Backfilled at the
pre-submission doc audit — every other Phase 2 ADR traces to a session here, and this one
did not: its trail lived only in `AI_LOG.md` P2 · c9 and the ADR itself.

The invocation was the standing gate instruction, not a bespoke prompt: run
`/security-review` before the gate (`brainstorm.md` §5, phases 1 and 3 — extended to
Phase 2 because the phase added authentication-adjacent surface). The review returned two
findings; both were reproduced before being believed, per the Correction #2 rule.

What made it architecture rather than a patch: both findings shared one root —
`users.id` is a SQLite rowid alias, so a deleted account's id is reissued, and sessions,
`?held_by=me`, and `audit_events` actors were all keyed on it. The prompt-shaped decision
was rejecting the local fix (`sqlite_autoincrement=True` changes only `CREATE TABLE` and
would have left the deployed volume vulnerable) for an identity decision: a per-account
session token issued once and never reissued, and soft-deleted accounts. → **ADR-0013**.

---

## Session 13 — 2026-08-07 — `mvp-reviewer` at the Phase 2 gate, and who owns the audit write — *verbatim*

**Status:** ✅ settled — an ADR-0010 invariant made structural. **Commits:** `8f127df`
(red), `e77355d` (green), `eb5b20a` (docs).

The gate ran twice. The invoking prompt both times:

> Use the mvp-reviewer agent for Phase 2.

First verdict: **FAIL** — a docs-only blocker (the README's graded sections still
described Phase 1) and, among the non-blockers, one that turned out to be design: the
route wrote the `audit_events` row and `rentals.force_return` accepted a `reason` it
ignored. The instruction that reopened the gate (verbatim):

> force_return ignores its reason param (app/rentals.py:191). Not cosmetic — ADR-0010
> makes the reason mandatory, and an override recorded without one defeats the table.
> Red test first, then fix.

The design consequence goes one level past the finding: rather than the route continuing
to write the event, the transition now writes its own record, in the same transaction as
the close — so no future caller of `rentals.force_return` (Phase 3's auditor is the
likely one) can end a rental and leave no trace. ADR-0010's mandatory reason moved from
convention (every caller remembers) to structure (the function cannot be called without
producing the row). Second verdict: **PASS WITH NOTES**, gate cleared, merged as PR #3,
tagged `v2-rental`.
