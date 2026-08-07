# Phase 3 — AI Layer + Production Hardening

Branch `phase-3-ai`. Settled by grilling 3 (`docs/PROMPT_TRAIL.md` Session 14) and
ADR-0014–0017, on top of ADR-0004 (settled since grilling 1, not relitigated).

**Sequenced to be cut, not squeezed.** Slice A and B must ship. Slice C is the first
thing to go, and inside C, the UI goes before the verb. Cutting means saying so in the
README `⚠️ Partial` section. Phase 4 (UI fidelity) is out of scope everywhere here.

Provider: **Gemini Flash**, key in `GEMINI_API_KEY`, server-side only, read at request
time (feature-off when absent — ADR-0016, never a boot refusal). The test suite never
calls the live API: the LLM client is one seam, mocked in every test (ADR-0004).

---

## Slice A — semantic search + announced fallback (must ship)

### The filter object — the only thing the model may say

One Pydantic schema, rejected wholesale on any validation failure (no partial
salvage — a half-valid filter is a wrong filter):

| field | type | notes |
| --- | --- | --- |
| `status` | `Status \| None` | the closed enum, unchanged |
| `needs_review` | `bool \| None` | the flag itself is public — its *reason* is not |
| `brand` | `str \| None` | case-insensitive equality |
| `name_contains` | `str \| None` | substring over `name` |
| `name_matches_any` | `list[str] \| None` | *(added post-gate)* the model's inferred product terms for a category query — "laptop" → `["MacBook", "XPS", …]`; OR within the list, case-insensitive, over `name` and `brand` only. The model contributes vocabulary, never results (ADR-0004), and the ADR-0015 oracle stays shut |
| `purchased_before` | `date \| None` | |
| `purchased_after` | `date \| None` | |
| `rentable_only` | `bool \| None` | `True` excludes `Repair` **and** flagged items — ADR-0003 through the same rule, not a parallel one |

**No predicate over `notes`, `history` or `review_reason` — for anyone (ADR-0015).**
The keyword fallback searches `name` and `brand` only, same rule, or the degraded path
leaks what the primary cannot.

### The route

`POST /api/search` `{"query": "<natural language>"}`, session required (ADR-0006).
Response: `{"mode": "semantic" | "keyword", "items": [...]}` — items through
`visible_to` (now in `app/domain.py`), so a `user` gets the restricted fields as
`null`. `mode` is asserted by tests, not just rows: a fallback that lies about being
the primary is the bug (ADR-0016). Timeout 12s, then fallback; API error, same;
key absent, same — always labelled. *(Amended from 5s at the live verification:
the provider's measured latency for one filter object is ~7.5s and its
thinking-off knob 400s, so 5s made the semantic path unreachable.)*

```
test_semantic_query_maps_to_filter_schema        # mocked LLM, deterministic
test_semantic_search_falls_back_on_api_error     # asserts mode == "keyword"
test_semantic_search_never_returns_unrentable_items  # rentable_only + ADR-0003
test_search_is_not_an_oracle_over_notes          # ADR-0015, both paths, user session
test_search_requires_a_session                   # ADR-0006
test_llm_key_absent_from_frontend_bundle         # secrets server-side only
```

## Slice B — the Inventory Auditor (must ship)

`GET /api/admin/audit` — **admin-only** (findings quote `notes`/`history`; derived
content inherits its source's restriction, ADR-0014). Computed per run, persisted
nowhere. Refuses `503` with a readable reason when the key is absent or the API fails
— **no keyword fallback** (ADR-0016): a degraded audit wearing the AI's name is worse
than a refusal.

Findings: `{"item_id", "kind", "evidence", "explanation"}` where `kind` is the closed
enum `status_contradiction | unidentifiable | probable_misspelling` (ADR-0014).
Off-enum kinds from the model are dropped and counted, never stored, never invented
into the enum.

**Required findings** (the mocked-model tests pin the plumbing; one optional live
smoke proves the prompt): id 5 and id 11 `status_contradiction`, id 10
`unidentifiable` — the judgment with no keyword signature — and id 9
`probable_misspelling` (`"Appel"`, closing ADR-0002's deferred typo). Id 6's future
date is *ingestion's* finding, already flagged at import; the auditor confirming it is
allowed, not pinned — one deliberate narrowing of `brainstorm.md` §3's list, because
re-asserting a structural check the quarantine already records proves nothing about
judgment.

```
test_auditor_flags_status_notes_contradiction    # ids 5, 11
test_auditor_flags_unidentifiable_item           # id 10 — no keyword signature
test_auditor_flags_misspelled_brand              # id 9 — ADR-0002's loop closes
test_auditor_is_admin_only                       # 403 for user, 401 anonymous
test_auditor_refuses_without_api_key             # 503 + reason, no fallback (ADR-0016)
test_auditor_drops_off_enum_finding_kinds        # closed vocabulary (ADR-0014)
test_auditor_writes_nothing                      # propose, never dispose: no needs_review,
                                                 # no review_reason, no rows anywhere
```

## Slice C — the flag-review verb + UI (first to cut; UI cut last inside C)

`POST /api/hardware/{item_id}/flag-review`, admin-only, mandatory reason (ADR-0017).
Sets `needs_review`, writes `review_reason` (the admin's text — human authors only,
never the model, ADR-0014), writes an `audit_events` row (`action` enum grows
`flag_review`). `409` on an already-flagged item — symmetric with `clear-review`
(ADR-0010): idempotency would file a mandatory reason against a non-event.

UI: findings listed on the admin panel; each carries a *Flag for review* action with
the reason prefilled from the finding, **editable before submit** — the recorded claim
is the human's (ADR-0017). Search box on the dashboard with the mode label
("keyword results — AI unavailable" when degraded).

```
test_admin_can_flag_item_for_review
test_flagging_blocks_rental                      # ADR-0003, the loop closes end to end
test_flag_review_requires_a_reason
test_flag_review_writes_an_audit_event           # actor, action, reason, item
test_flag_review_409_when_already_flagged
test_non_admin_cannot_flag
```

## Production hardening — gate checklist, not a slice

- [ ] `GET /api/health` → `200 {"status": "ok"}`, no session required (the one
      deliberate exception to ADR-0006 besides `GET /` — it must answer while the
      database is broken, so it touches nothing)
- [ ] `test_prod_config_requires_secret_key` still green; `GEMINI_API_KEY` confirmed
      absent from the built bundle and from every response body
- [ ] `smoke_deployed_login_and_rent_flow` against the live URL after deploy
- [ ] README: live-versions row for v3, graded sections updated — including `mode`
      honesty under ✅ and whatever Slice C's fate was under ⚠️

CI and the vitest suite stay README-🔮-owed; they ride this checklist only if the
budget allows after Slice C's fate is decided.

## Commit shape

Three: `test(phase-3)` red (test-author), `feat(phase-3)` green (/tdd),
`chore(phase-3)` deploy v3. `mvp-reviewer` at the gate.
