# Hardware Hub — Build Plan (v2)

**Project:** Booksy Early Careers recruitment task
**Method:** TDD, branch-per-phase, human review gate between versions
**Stack:** FastAPI + SQLite, Vue 3 + Vite, **single origin** (FastAPI serves the built bundle)
**Skills:** `/grill-me` · `/tdd` · `/improve-codebase-architecture` · `frontend-design` · `/security-review`

> **v2 supersedes v1.** Four phases, not six. Changes came out of the whole-project
> grilling session — see `docs/PROMPT_TRAIL.md` and ADRs 0001–0005. The v1 plan had
> roughly 3.5 hours of process overhead inside a 4–5 hour budget; that was the
> central flaw and it is fixed here by collapsing phases, not by cutting rigor.

> **Status note, 2026-08-07 (v2 shipped, unrewritten below).** This plan predates
> ADR-0006–0013; where they disagree, the ADRs win. Known drift, left in place because
> the plan is a record of what was planned: the 15–20 commit target was missed at 41
> (owned in the README ⚡ section, with why); Phase 2 shipped wider than §3 describes —
> an `audit_events` table, force-return, soft-deleted accounts (ADR-0013), field-level
> visibility (ADR-0012), and a demo reset route; the §7 open item on the authorization
> enforcement point settled as per-route dependencies in Phase 1; and the documented
> manual reseed is gone — `persist` refuses while rentals exist (ADR-0011). **Phase 3
> shipped 2026-08-07 (v3 live):** semantic search, the Inventory Auditor and the
> flag-review verb, verified on the deployment — the auditor flags id 10 and id 9's
> `"Appel"`. CI and vitest remained unbuilt through Phase 3 — the README 🔮 section
> owns them now. Phase 4 (§3) is planned and untouched.

---

## 0. Ground Rules

| Rule | In practice |
|---|---|
| **Grill before building** | One whole-project grilling (done) + one each for MVP 2 and MVP 3. Phase 0 and MVP 1 are settled by the first session. |
| **Red → Green → Refactor** | `/tdd` drives implementation. No production code before a failing test. |
| **One branch per phase** | Five branches, five gates (Phase 4 added 2026-08-07). Merged to `main` only after your review. |
| **Deploy every phase** | Live URL after each, recorded in the README. |
| **AI log per commit — two formats** | Three lines for routine commits; long-form only for genuine corrections. §4. |
| **15–20 commits** | ~4 per phase. |
| **Honesty is a feature** | Shortcuts enter the README trade-offs table when taken. |

### Commits per phase (~4 × 4 = 16)

1. `test(phase-N): <failing specs>` — red
2. `feat(phase-N): <implementation>` — green
3. `refactor(phase-N): ...` — only if the architecture pass demands it
4. `chore(phase-N): deploy vN + docs` — live URL, README, tag

---

## 1. Decisions Settled by the Grilling

These are load-bearing. Each gets an ADR before Phase 0 code.

### ADR-0001 — Single origin

FastAPI mounts the built Vue `dist/` as static files. One service, one URL, one
env var set, SQLite on a Railway persistent volume.

**Why:** removes CORS entirely, makes cookies same-site by definition, and deletes
a whole class of configuration that has to be right under time pressure. Split
origin (Vercel + Railway) buys nothing here and costs `SameSite=None; Secure`
plus CSRF handling.

**Consequence:** `test_cors_rejects_unknown_origin` is deleted. Under single
origin there is no cross-origin path to reject, and a test asserting an
unreachable condition reads as cargo cult. Replaced with a real authorization test.

### ADR-0002 — Ingestion validates structure only

Ingestion checks schema, enum membership, key uniqueness, and date validity.
**Semantic contradiction is explicitly out of its remit.** A validation layer does
not make judgement calls about whether "battery swelling" means an item is unsafe.

**Why this boundary is declared, not accidental:** without it, the two contradictory
seed records look like a problem manufactured so the AI could solve it — the most
damaging possible reading of an AI submission. With it, the division of labour is
principled: deterministic validation handles structure, the LLM handles judgement.

### ADR-0003 — `needs_review` is a rentability guard, not a badge

A flagged item **cannot be rented**. Attempting it returns `409` with a readable
reason, through the same guard machinery as `Repair`.

**Why:** v1 preserved the Dell XPS (swelling battery, marked `Available`) and the
MacBook Air (liquid damage, marked `Available`) so the auditor would have something
to find — while building a rental engine that would cheerfully issue both. That
subordinates product safety to a demo moment. This closes the hole without losing
the demo: the items stay in the database, stay visible, stay unrentable, and the
auditor still explains *why* in language a keyword scan could not produce.

**A flag that changes nothing is decoration.** This one changes rentability.

### ADR-0004 — Structured filter extraction over prompt-stuffing

The LLM emits a schema-validated filter object; SQLite returns the rows.

**Why — two reasons that survive at any scale:**

1. **The model cannot hallucinate inventory.** Every item a user sees provably
   exists in the database. Hand the model the catalogue and it can invent a
   fourteenth device, and nothing prevents it.
2. **The AI layer becomes unit-testable.** A deterministic object asserted against
   a mocked LLM. "Model reads catalogue, returns prose" is testable only by
   snapshot, which is barely.

Scale is a footnote, not the argument. "Only 12 records" collapses the moment
someone asks about 12,000.

**Framing note:** don't claim "AI-native" as an architectural property — two
features on a CRUD app is AI-*featured*. Let the engineering carry it instead:
schema-validated output, guaranteed-real results, graceful fallback, deterministic
tests. State that positively; don't editorialise about the brief's wording.

### ADR-0005 — Admin bootstrap and the zero-admin invariant

Seed creates admin #1 from `ADMIN_EMAIL` / `ADMIN_PASSWORD`. The app **refuses to
boot in production** if `ADMIN_PASSWORD` is unset — same shape as the secret-key check.

**"At least one admin exists" is a guard in the same layer as the rental guards**,
returning `409`. It is the same class of invariant and must not live somewhere else.
Without it, an admin can demote or delete themselves and lock the system permanently
in two clicks — an impossible state, in the app whose pitch is that impossible states
are unreachable.

A **separate demo account** goes in the README, not the real admin credentials.
Listed in the trade-offs table as a deliberate affordance on a public deployment.

---

## 2. Seed Data Audit

11 records, ids 1,2,3,4,5,6,7,**4**,9,10,11 → only 10 unique.

| # | Record | Defect | Handled by |
|---|---|---|---|
| 1 | id `4` twice | Primary-key collision | Re-key to 12, keep `source_id` |
| 2 | id `8` missing | Sequence gap | Noted, no action |
| 3 | id `6` — `purchaseDate: 2027-10-10` | Future date | Quarantine + `needs_review` |
| 4 | id `9` — `"22-05-2023"` | DD-MM-YYYY vs ISO | Normalise |
| 5 | id `9` — `brand: "Appel"` | Typo | **Not ingestion's job** (ADR-0002) → auditor |
| 6 | id `10` — `""`, `null`, `"Unknown"` | Empty + null + off-enum | Quarantine + `needs_review` |
| 7 | id `5` Dell XPS — `Available` + "battery swelling" | **Semantic** | **Not ingestion's job** (ADR-0002) → auditor |
| 8 | id `11` MacBook Air — `Available` + liquid damage | **Semantic** | Same |
| 9 | id `2` `In Use`, no `assignedTo` | Orphan rental | Resolved at import |
| 10 | Optional fields on some records only | Non-uniform schema | Nullable columns |

**Nothing is deleted.** Rejected rows go to `hardware_quarantine` with a reason.

**The auditor must flag id 10** — empty brand, null date, unidentifiable → *"needs
physical audit."* That judgement has **no keyword signature**, which is what proves
the AI layer isn't a regex. Say plainly in the README that a keyword scan would have
caught the two obvious ones; id 10 is the one it wouldn't.

---

## 3. The Phases (four planned; Phase 4 added 2026-08-07)

Each: branch → red → green → deploy → gate → merge → tag.

### Phase 0 — Foundation, Data Audit, First Deploy

Branch `phase-0-foundation`. Settled by the whole-project grilling; no separate session.

- Scaffold, single-origin wiring (FastAPI serves `dist/`), pytest + vitest, CI
- `scripts/seed.py` — quarantine importer, admin from env
- `docs/DATA_AUDIT.md`, ADRs 0001–0005
- **Deploy v0** — proves the pipeline before there is anything to lose

```
test_seed_rekeys_duplicate_id
test_seed_normalises_date_formats
test_seed_quarantines_unknown_status
test_seed_flags_future_purchase_date
test_app_refuses_to_boot_without_admin_password
```

### Phase 1 — Auth, Admin Command Center, Dashboard

Branch `phase-1-admin`. Also settled by the first grilling. Skills: `/tdd`, `frontend-design`, `/security-review`.

- Login, session cookie (same-site, free under single origin), `admin` / `user` roles
- Admin: add / delete hardware, toggle Repair, create accounts
- Dashboard: Name / Brand / Purchase Date / Status, sortable + filterable
- `needs_review` queue surfaced

```
test_login_rejects_unknown_user
test_login_rejects_wrong_password
test_non_admin_cannot_create_user
test_non_admin_cannot_delete_hardware
test_cannot_remove_last_admin              # ADR-0005 — the zero-admin invariant
test_admin_can_toggle_repair_status
test_dashboard_sorts_by_purchase_date
test_dashboard_filters_by_status
test_password_is_hashed_not_stored_plaintext
```

Run `/security-review` before the gate. Start `docs/WIREFRAME_JUSTIFICATION.md` here.

### Phase 2 — Rental Engine

Branch `phase-2-rental`. **`/grill-me` first.** Then `/tdd`, then `/improve-codebase-architecture`.

- Rent / Return, state machine as single source of truth
- Rental history table (MVP 3 feeds on it)
- Guards: Repair, already-rented, wrong-user, **`needs_review`**, last-admin
- **Clearing `needs_review`** — an admin action, with an audit trail, gated on the same
  guard layer. Inherited from Phase 1, which surfaced the queue read-only; ADR-0003
  assigns the mechanism here because clearing the flag is a transition in this state
  machine, not an admin-panel field edit

```
Available ──rent──▶ In Use ──return──▶ Available
    │                                      │
    └──────── admin toggle ───▶ Repair ◀───┘

needs_review ──▶ blocked from rent, 409 with reason
```

```
test_cannot_rent_hardware_in_repair
test_cannot_rent_flagged_hardware           # ADR-0003 — Dell XPS stays unrentable
test_cannot_rent_hardware_already_in_use
test_cannot_return_hardware_not_rented
test_cannot_return_someone_elses_rental
test_rent_then_return_restores_available
test_concurrent_rent_only_one_succeeds      # atomic conditional UPDATE
test_rental_history_records_both_ends
test_admin_can_clear_needs_review          # ADR-0003 — admin only, leaves an audit trail
test_cleared_item_becomes_rentable         # ADR-0003 — a flag that clears but still blocks is decoration
```

**The architecture pass here is load-bearing.** Transition logic must not leak into
route handlers, or Phase 3 gets built on sand.

### Phase 3 — AI Layer + Production Hardening

Branch `phase-3-ai`. **`/grill-me` first.** Then `/tdd`, `/improve-codebase-architecture`, `/security-review`.

**Semantic search** — natural language → filter object → SQLite (ADR-0004).
**Inventory Auditor** — flags the Dell XPS, the MacBook Air, the 2027 date,
**id 10** (the one with no keyword signature), and **id 9's brand `"Appel"`** as a
probable misspelling of Apple. The typo is the one defect ADR-0002 named and deliberately
declined to fix at ingestion, on the grounds that correcting a spelling is judgement
rather than structure — so the auditor surfacing it is what closes that loop. Leaving it
unfound would mean ingestion skipped it *and* nothing ever caught it, which reads as an
oversight rather than the decision it was.

Production hardening folds in here as a gate checklist, not a phase: secrets in env,
persistent volume, documented reseed, health endpoint, demo credentials in README,
smoke test against the deployed URL.

```
test_semantic_query_maps_to_filter_schema    # mocked LLM, deterministic
test_semantic_search_falls_back_on_api_error
test_semantic_search_never_returns_unrentable_items
test_auditor_flags_status_notes_contradiction
test_auditor_flags_unidentifiable_item       # id 10 — no keyword signature
test_auditor_flags_misspelled_brand          # id 9 "Appel" — ADR-0002's deferred typo
test_llm_key_absent_from_frontend_bundle
test_health_endpoint_returns_ok
test_prod_config_requires_secret_key
smoke_deployed_login_and_rent_flow
```

### Phase 4 — Wireframe Fidelity *(added 2026-08-07, extended same day — does not start until Phase 3 ships)*

Branch `phase-4-ui`. Goal: the app is a **close copy** of the supplied wireframes in
`docs/wireframes/` (local, gitignored — they are confidential). Read every screenshot
carefully before writing anything — layout, spacing, type scale, weights, control
placement. **Fidelity is the objective, not inspiration.**

**Slice C precondition — confirmed shipped.** The admin flag-review verb landed in
Phase 3 (`feat(phase-3): admin flag-review verb`, six tests, live). Had it been cut it
would sit here as a must-ship, because without it flagging is seed-only: ingestion
flags at import, the add form rejects rather than flags, and the auditor cannot flag
by design (ADR-0014) — a finding could never make an item unrentable. The README now
documents the full chain so a reviewer can see how anything enters review after
import.

**The table:**

- Remove the review column entirely. A flagged row shows the amber **!** where the
  Rent button would be — no button at all; the **!** is the affordance, a tooltip
  explains. Keyboard-reachable and screen-reader labelled, not hover-only.
  *(Supersedes the earlier "badge before the device name" placement.)*
- Rented rows: users see "Rented" with no holder; admins see the holder's email.
  Keeps the ADR-0012 amendment; "somebody else has it" is gone either way.
- Display `In Use` as "Rented". **Display label only** — the stored enum stays
  `Available | In Use | Repair` per the brief and every ADR. Map at the view layer.
- Every button the same width, height and font size — Rent, Repair, Edit, Remove.
  Bigger than current: **32px minimum touch target**.
- Correct Tabler glyphs for Repair, Edit, Remove, matching the wireframe.
- Sorting works both directions on every sortable column, including alphabetical on
  name and brand. Closes the descending-sort question open in `BACKLOG.md` since
  Phase 1 — pick a convention, pin it with a test, delete the entry.
- "Inventory" heading becomes "Hardware List". No subtitle. Match the prototype's
  font sizes and weights exactly.

**Needs-review tab — separate view, not a filter.** Carries the review column, the
reason text, and the Review action. The Review action exists **only** here — never in
the main table. Empty state: "No items awaiting review." After a successful Review,
the row shows a resolved state for 2 seconds, then fades out — the admin sees the
result rather than watching it vanish.

**Admin edit** — name, brand, purchase date, serial, category. Moves from README ⚠️
to ✅. Record in `docs/WIREFRAME_JUSTIFICATION.md` that the brief scopes admin actions
to add/delete/toggle-Repair, so edit is **wireframe-driven, not brief-required**.

**Review resolution note — amends ADR-0017.** Clearing `needs_review` takes a reason
that must begin with `fixed:` — e.g. "fixed: battery replaced, safe to issue".
Validated server-side, `422` otherwise. The amendment's claim: an admin must state
what changed, not merely that they looked.

**Add New Device modal:** match the wireframe — Name, Serial Number, Brand, Category
dropdown (Laptop / Mobile / Tablet / Monitor / Accessory). Admin panel: match the
wireframe exactly.

**Schema — needs a migration test (CLAUDE.md, mandatory):**

- `serial_number`, `category` (closed enum, the five values above), `date_added`
  (defaults to now on create).
- The seed's 11 records have none of these: `serial_number` and `category` `NULL`,
  `date_added` backfilled from `purchase_date`. Update `docs/DATA_AUDIT.md`.
- The migration test boots over the *Phase 3* table shape in raw SQL and asserts a
  real request succeeds.

**Kept because the brief requires them — wireframe deviations, recorded in
`docs/WIREFRAME_JUSTIFICATION.md` as brief-mandated so a reviewer sees they were
deliberate:**

- **Purchase Date column stays.** The brief names it explicitly: "showing Name, Brand,
  Purchase Date, and Status". Date Added is an additional column, not a replacement.
- **Filtering stays.** The brief: "Must support sorting and filtering."

**Renter identity hidden — amends ADR-0012.** The wireframe does not show who holds an
item; ADR-0012 decided the opposite, with reasoning (knowing who to ask). Write the
amendment rather than silently reversing: the item still shows Rented, the holder is
admin-only (which is what the table rules above implement).

**Sounds and toasts — four events:**

- Admin, rent happened: toast + soft chime.
- Admin, item entered review: toast + distinct, slightly more urgent tone.
- User, own action confirmed: short click on successful rent or return.
- Anyone, `409` refusal: low tone.

All muteable, **off by default**, respect `prefers-reduced-motion`, and never the only
signal — the toast carries the information. Delivery mechanism is a design decision:
polling is acceptable for a demo, but say so in an ADR rather than reaching for
websockets.

**Scope: desktop only.** State it in the README rather than leaving it to be
discovered — an internal tool with six columns is a legitimate desktop-first decision.

**Skills and agents:** `frontend-design` for every visual item — feed it the
screenshots and the constraint that fidelity beats expressiveness here. `test-author`
then `/tdd` for the schema slice, migration test included. `mvp-reviewer` at the gate.
No `architecture-scout` — this phase adds no new seams.

**Cut order if time runs out:** sounds first, then Date Added, then the notification
toasts. The visual fidelity items are cheap and are what a reviewer sees. Schema
changes keep their migration test whatever else is cut.

### Final polish — one commit, not a phase

`docs: final polish` on `main`: README (setup, live-versions table, ✅/⚡/⚠️/🔮),
`AI_LOG.md` read-through, `PROMPT_TRAIL.md`, `WIREFRAME_JUSTIFICATION.md`, empty
states, favicon, GIF of the auditor. Then `/grill-me` on your own submission as
interview prep.

---

## 4. The AI Log — Two Formats

Twenty uniform nine-line entries is itself the texture that reads as batch-written.

**Routine commits — three lines:**

```markdown
## [P1 · c2] Admin CRUD + role guards
/tdd against the phase-1 spec. Clean run, no corrections needed.
Commit: feat(phase-1): admin hardware and account management (a1b2c3d)
```

**Corrections — long form, and rare.** Reserve for genuine moments where the AI was
wrong: what it produced, why it was wrong, how you caught it, how you corrected it.
Target **three or four across the whole build**. The brief asks for the correction
narrative; it does not ask for twenty of them.

**Correction #1 is already written and dated** — the whole-project grilling caught
that v1's preserved seed contradictions were rentable, subordinating product safety
to a demo moment. Fixed by ADR-0002 + ADR-0003. Log it now, while the shape is fresh.

---

## 5. Review Gate (four times)

**Automated — opens the gate:** tests green · lint clean · CI green · vN live.

**Yours — is the gate:**

```
[ ] Read the PR diff end to end. Anything you cannot explain does not merge.
[ ] Click through live vN. Does it behave as intended?
[ ] Do the tests test behaviour, or implementation?
[ ] /security-review run (phases 1 and 3)?
[ ] Architecture report reviewed, actions decided (phases 2 and 3)?
[ ] AI_LOG.md current. Shortcuts in the README table. UI deviations recorded.
```

✅ merge, tag, next branch · 🔄 fix commit, re-gate · ⛔ cut scope

---

## 6. Scope Control

Cut in this order, and record every cut in ⚠️ Partial/Missing:

1. Frontend polish pass
2. Auditor reduced to the two keyword-findable items (but then **say** the AI layer
   is doing less than intended — do not let id 10 quietly vanish)
3. CI automation (keep the tests)
4. Architecture pass in Phase 3 (keep Phase 2's — it is load-bearing)

**Never cut:** the tests, the AI log, the review gates, the two remaining grillings.

---

## 7. Open Items

- **Wireframes** — feed `frontend-design` in Phase 1; deviations logged as made
- **LLM provider** — Gemini Flash / Claude Haiku / GPT-4o-mini. Decide before Phase 3.
  Under ADR-0004 any of them works; the schema does the load-bearing work.
- **Authorization enforcement point** — per-route dependency vs middleware. Settle in
  Phase 1's first commit now that ADR-0001 fixes it as a cookie.
