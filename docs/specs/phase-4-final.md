# Phase 4: the final push

Planning pass, 2026-08-07. Every item below was checked against the repository rather
than against the request that named it. Three of the eleven are already built, one should
not be built as written, and one cannot start until another finishes.

This file also closes `BACKLOG.md` → *"No `docs/specs/phase-4.md`"*; retire that entry
when this one lands, or Phase 4 stays listed as unspecified in a document a reviewer
reads.

---

## Status of each item, with evidence

### FEATURE

**1. Return with an issue. NOT STARTED.**
`grep` for `report a problem` / `return_with_issue` / `anything wrong` across `app/`,
`frontend/src/`, `tests/` and `docs/` returns nothing. `POST /api/hardware/{id}/return`
(`app/main.py:700`) takes no body. `README.md:292` carries it as 🔮 Next Steps #3,
already naming seed id 11's history as the loop it closes, so the framing is written and
the feature is not.

The ADR is **0020**; `docs/adr/` stops at 0019.

Its argument has to do one specific job: distinguish itself from **ADR-0014**, *the
auditor proposes, never disposes*. That ADR denies write access to a judge that reasons
over text. A returner held the equipment, so the justification is not "humans outrank
models". It is that **direct observation licenses direct action, and inference does
not**. State it that way or ADR-0014 reads as arbitrary in hindsight.

Two consequences worth naming in the ADR rather than discovering later:
- **ADR-0003** makes `needs_review` block rental, so a reported item becomes unrentable
  the instant it is handed back. That is the desired behaviour and should be claimed,
  not left to be noticed.
- **ADR-0017's** amendment requires a flag reason authored by a human. The returner's
  note satisfies it directly, and the new Repair outcome is how an admin then concludes
  the review the return opened. The loop is: returner observes → flags with a note →
  admin concludes in Release or Repair.

### FINISH

**2. Ask AI focus ring. PARTLY BUILT, and contradicting itself.**

The premise in the request is wrong in a way that matters: the blue is **not** the
browser default. `--focus: #2563eb` is a project token (`styles.css:63`, dark `:115`),
and it is the shared focus colour for every interactive element in the tool
(`styles.css:149`). Blue appears nowhere else in the *palette*, but it appears
everywhere in the *focus layer*, deliberately.

What is actually wrong is a specificity collision. Two rules target the same element:

| Line | Rule | Effect |
| --- | --- | --- |
| 1080 | `.search-bar input[type='search']:focus-visible` | `border-color: var(--line-strong)`, `background: var(--surface)` |
| 1207 | `.search-bar input[type='search']:focus-visible` | `border: 0`, `background: var(--ask-fill)`, `outline: 2px solid var(--focus)`, `outline-offset: 2px` |

**The treatment being asked for was already written at 1080 and is overridden 127 lines
later by 1206.** The later block resets the border to `0` and reinstates the detached
ring. The fix is to make 1207 carry the fill-and-border shift rather than deleting 1080.

One constraint the request does not mention and the work must respect: this is the
*only* focus indicator on the bar. Replacing a 2px ring with a fill change is a WCAG
**2.4.11 Focus Appearance** question rather than a taste question, so the new indicator
must reach **3:1** against both the unfocused state and the surrounding surface. Measure
it into `docs/ACCESSIBILITY.md` in the same pass, or the palette complaint is traded for
an accessibility regression that no test would catch.

**3. Status column centred. NOT STARTED.**
`HardwareTable.vue:208` is `<td><StatusChip :status="item.status" /></td>`, with no class,
and no `.cell-status` rule exists in `styles.css`. Needs the class and one
`text-align: center`, on the header cell too or the column reads misaligned.

**4. Larger logo. ALREADY BUILT.**
`styles.css:189` sets `.brand-mark` to 34px; the *"Phase 4, finish II"* block at
`styles.css:1050` overrides it to 44px, with the comment *"at 34px it read as a favicon
that had wandered into the sidebar"*. Still listed as outstanding. **Verify visually at
the deploy and strike it**, or say what 44px still gets wrong, because "larger" has
already been applied once.

**5. Darker primary text. SHOULD NOT BE BUILT AS SPECIFIED.**
`--ink: #0b0c10` (`styles.css:32`) is very near black: roughly **19.6:1** on white,
about 2.6× the AA requirement of 4.5:1. There is no headroom, so darkening it further is
imperceptible and cannot improve any measurement.

The text that is actually close to the line is the secondary layer:
`--ink-muted: #5b6270` and `--ink-faint: #6a7283`, the latter already annotated in the
token as **4.83:1 on card, 4.55:1 on page**, passing, with the page figure 0.05
above the threshold. If "primary text feels light" came from reading the table, the
cause is almost certainly `--ink-muted` on the brand and date columns, not `--ink`.

**Recommendation: retarget this item to `--ink-muted` / `--ink-faint`, or drop it.**
Building it as written is a no-op that would still cost an ACCESSIBILITY re-measure.

**6. More horizontal page padding. ALREADY BUILT ONCE.**
`.main` is `padding: 26px 30px 60px` at `styles.css:258`; `styles.css:1113` overrides
`padding-left`/`padding-right` to **40px**. Still listed as outstanding. Treat as a
judgement call at the deploy: if 40px is still tight, raise it deliberately with a
number, rather than as an unbounded "more".

### DOCS

**7. Back-annotate `(pending)` SHAs. NOT STARTED, and the count is 26, not 24.**
`grep -c "^Commit:.*(pending)" AI_LOG.md` → **26**. (29 lines contain the word overall;
the other three are prose.) One `Edit` call each, per the never-`sed` non-negotiable.

**8. `PROMPT_TRAIL.md` 15 → 20. NOT STARTED, and it is blocked by item 1.**
`grep -c "^## Session"` → **15**. The list in the request names ADR-**0020**, which does
not exist yet: this item cannot complete before the return-with-issue ADR is written.
Sequence it after item 1, and note that this planning session is itself one of the
sessions to record.

**9. Consolidate the instrument errors. PARTLY BUILT.**
`AI_LOG.md:1687` already reads *"Correction candidate, three instrument errors, one
family"*, and `:1722` records the fourth. Correction #6 adds the three live-state
inferences. The material exists in three places; the job is **merging them into one
entry and leaving pointers**, not writing it from scratch. Cheaper than it looks.

**10. Fresh-clone check. NOT STARTED.**
Prediction to verify rather than assume: `dist/` is gitignored (`.gitignore`), and
`test_serves_built_bundle_at_root` needs a real one. `README.md:333-338` does order
`npm run build` before `uvicorn`, but a reviewer whose first instinct is `pytest`, which
is the instinct this project has trained, hits a failure the README never warns about.
That is the most likely first failing step. Clone, follow it literally, report what breaks.

### DEPLOY

**11. v4 deploy. NOT STARTED.**
`README.md:27` still reads `| v4 | Phase 4, wireframe fidelity | | 🔮 planned, after
v3 |`, and row 26 has v3 on the live URL. `tests/test_smoke_deployed.py` now exists to
gate it, which it did not at any previous deploy. Both themes verified live, and the
README table updated in the same commit.

---

## Flags

**Specified twice.** Items 4 and 6 are both already shipped and both still listed as
outstanding, so a second "make it larger / add more padding" pass without a target number
would either no-op or overshoot silently.

**Contradicting a shipped decision.** None outright, but item 1 sits directly against
ADR-0014 and will read as a contradiction to anybody who reads the ADRs in order unless
ADR-0020 draws the observation-versus-inference line explicitly.

**Should not be built.** Item 5 as written (see above).

**Blocked.** Item 8 by item 1.

**Already done, still listed elsewhere.** `BACKLOG.md` still carries *"No
`docs/specs/phase-4.md`"*; `README.md:292` still carries return-with-issue under 🔮 and
must move to ✅ as part of item 1, not as a separate tidy-up.

---

## Sequence

### Batch A: the product claim
1. **Item 1**, red first: return-with-issue, `ADR-0020`, README 🔮 → ✅.
2. **Item 3**, status centring (trivial, ships alongside).

### Batch B: the finish, measured
3. **Item 2**, focus indicator: fix the 1207 override, then measure it into
   `ACCESSIBILITY.md` against WCAG 2.4.11.
4. **Item 5**, *retargeted* to `--ink-muted` / `--ink-faint`, or formally dropped.
5. **Items 4 and 6**, visual confirmation only, with no code unless a number is named.

### Batch C: the record, then ship
6. **Item 7**, 26 SHAs.
7. **Item 8**, PROMPT_TRAIL to 20 (needs ADR-0020 from Batch A).
8. **Item 11**, `npm run build` → `railway up --detach` → **smoke check against the live
   URL** → both themes → README table.

> ### ─────────── CUT LINE ───────────
>
> Everything above ships. Below is real work that a reviewer will not miss if the clock
> runs out, because nothing in the product or its documentation is *wrong* without it.

9. **Item 9**, consolidating the instrument errors. The material is already in the log
   in three places and each is individually correct; merging them is an improvement in
   readability, not in accuracy.
10. **Item 10**, the fresh-clone check. Highest value of anything below the line, and
    the first candidate to pull back above it if Batch B lands early. It is also the
    only item here that can *find* a defect rather than tidy one.

**Deploy is the last action either way.** If the clock runs out mid-Batch C, item 11
still happens, because an unshipped v4 is the one outcome that makes the rest of this
pointless.
