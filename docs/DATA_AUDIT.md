# Data Audit: what the seed contained and what ingestion did

The brief supplied 11 records in `data/seed.json`, committed **verbatim and never
modified**: every defect in it is intentional input. This document records what was
wrong with each row and what ingestion did about it.

**This document is enforced, not just written.**
`test_importer_reproduces_documented_audit` runs the real `data/seed.json` through
the importer and asserts the numbers below line by line. If the seed file or the
importer drifts apart from this page, that test goes red. Every figure here is
transcribed from the green suite, not from the plan.

**Result:** 11 seed rows in, **11 hardware items** out, **3 quarantine records**.
Nothing was deleted.

---

## The ten defect classes

Numbered as in `brainstorm.md` §2.

| # | Record | Defect | What ingestion did |
|---|---|---|---|
| 1 | `id: 4` appears twice | Primary-key collision | Second occurrence re-keyed to **12**, original kept as `source_id: 4`. Both rows imported. |
| 2 | `id: 8` absent | Sequence gap | Nothing. A gap is not a defect in any row. |
| 3 | `id: 6`, `purchaseDate: "2027-10-10"` | Date in the future | **Quarantined** with a reason; item imported and flagged `needs_review`. |
| 4 | `id: 9`, `"22-05-2023"` | `DD-MM-YYYY` among ISO dates | Normalised to `2023-05-22`. Not quarantined, not flagged. |
| 5 | `id: 9`, `brand: "Appel"` | Typo | **Left exactly as written.** See the boundary below. |
| 6 | `id: 10`, `""`, `null`, `"Unknown"` | Empty brand, null date, off-enum status | **Quarantined** with a reason; imported as `Available` + `needs_review`. Empty brand and null date are nullable, not errors. |
| 7 | `id: 5` Dell XPS 15 9510, `Available` with notes reading "Battery swelling, do not issue without service." | Semantic contradiction | **Nothing.** See the boundary below. |
| 8 | `id: 11` MacBook Air M2, `Available` with a history of liquid damage | Semantic contradiction | **Nothing.** Same. |
| 9 | `id: 2`, `In Use` with no `assignedTo` | Orphan rental | Released to `Available` and **quarantined** with a reason. Not flagged. |
| 10 | `notes` / `assignedTo` / `history` present on some rows only | Non-uniform schema | Nullable columns. Absence is not an error. |

---

## The quarantine trail

Three records, each carrying a readable reason and the original row verbatim as
evidence.

| Seed id | `needs_review` | Reason as stored |
|---|---|---|
| 2 | **`False`** | seed claimed status 'In Use' but named no assignee; the renter could not be reconstructed, so the orphan rental was released and the item imported as Available |
| 6 | `True` | purchase date 2027-10-10 is in the future |
| 10 | `True` | status 'Unknown' is not a recognised status (Available, In Use, Repair) |

### Quarantined does not mean unrentable

Id 2 is quarantined and **rentable**. Ids 6 and 10 are quarantined and **blocked**.

The two signals are deliberately separate. A quarantine record says *this row
diverged from the seed, and here is why*. `needs_review` says *a human must decide
something before this item can be rented*, and under ADR-0003 it is a rentability
guard returning `409`.

An orphan rental is **fully repaired** by releasing it: there is nothing left for
anyone to rule on, so flagging it would make a working MacBook unrentable over
missing paperwork. A future purchase date and an unidentifiable device both leave a
real open question, so they are flagged as well as recorded.

---

## Where the stored data differs from the seed

Four rows. Everything else round-trips unchanged.

| Seed id | Change |
|---|---|
| 2 | `status` `"In Use"` → `"Available"`, orphan rental released |
| 4 (second occurrence) | `id` `4` → `12`, with `source_id: 4` |
| 9 | `purchaseDate` `"22-05-2023"` → `2023-05-22`, format normalised |
| 10 | `status` `"Unknown"` → `"Available"` |

Two notes on this table, both load-bearing:

- **The re-key produces no quarantine record.** Nothing was rejected: the row was
  repaired and both copies survive with their provenance intact.
  `test_seed_rekeys_duplicate_id` asserts the quarantine table stays empty for it.
- **`"Unknown"` maps to `Available`, never `Repair`.** The seed tells us the record
  is unidentifiable, not that the item is broken, and `Repair` would assert a
  physical fact nothing evidences. Rentability does not depend on the choice, since
  `needs_review` blocks the item either way, so the status carries the weakest
  claim the evidence supports (ADR-0002).

---

## The boundary: what ingestion deliberately did not do

**Ingestion validates structure only** (ADR-0002): schema shape, enum membership,
primary-key uniqueness, date format, date plausibility. Semantic judgement over
free-text `notes` and `history` is explicitly outside its remit.

Three rows were left alone on that basis.

**`brand: "Appel"` (id 9).** Parsing a field is structural; correcting a value is
not. Reading `"22-05-2023"` as a date is deterministic because 22 cannot be a month, so
the string has exactly one legal reading, and normalising it loses nothing. (The
rule is one-legal-reading, not two-candidate-formats: a date like `"05-04-2023"`
reads both ways and quarantines instead, per ADR-0002 as amended.) Reading
`"Appel"` as `"Apple"` is a guess about intent, correct only because a human
recognises the brand. The typo is the Inventory Auditor's to surface.
`test_seed_imports_non_iso_date_without_quarantining` pins both halves on this one
row: the date normalises, the brand survives untouched.

**The Dell XPS (id 5) and the MacBook Air (id 11).** Both are `Available` while
their own free text says otherwise. Both were imported as written, unflagged and
unquarantined. `test_seed_ignores_semantic_contradiction_in_notes` exists to go red
if ingestion ever grows a keyword scan.

### Why this boundary is declared rather than convenient

"Battery swelling" and "liquid damage" are keyword-findable. **A keyword scan would
have caught both.** If ingestion *could* have detected them and was written not to,
the problem the AI layer solves would have been manufactured for it to solve.

So the division of labour is stated up front: deterministic validation handles
structure, judgement is a separate layer that can fail, time out, or be wrong. The
cost is accepted openly: a structural validator passes any record whose fields are
individually well-formed but collectively nonsensical.

That commits the auditor to something harder than the two obvious rows. **Record 10
is the test.** Empty brand, null purchase date, `"Unknown"` status, no notes at all:
unidentifiable, and needing a physical audit. That judgement has no keyword
signature, and it is what shows whether the AI layer does anything a regex
could not. *(It did: v3's live auditor reports record 10 as `unidentifiable` and
id 9's `"Appel"` as `probable_misspelling`, the finding this document deferred
to it and the one ADR-0002 deliberately left unfixed.)*

### Safety is not addressed by this boundary

ADR-0002 leaves both contradictory records `Available` and, on its own, rentable.
That hole is closed by ADR-0003, and the two must be read together: the records
stay in the database, stay visible, and become unrentable through the guard layer
rather than through ingestion.

---

## Enforcement

| Test | What it holds |
|---|---|
| `test_importer_reproduces_documented_audit` | The whole page: 11 imported, quarantine for ids 2, 6, 10, id 4 re-keyed to 12 with `source_id`, `"Appel"` preserved, both contradictions `Available` and unflagged |
| `test_seed_rekeys_duplicate_id` | Re-key preserves `source_id`, drops nothing, quarantines nothing |
| `test_seed_normalises_date_formats` | ISO and `DD-MM-YYYY` both parse; null and empty yield no date |
| `test_seed_quarantines_unknown_status` | Off-enum status → quarantine + `Available` + `needs_review` |
| `test_seed_flags_future_purchase_date` | Future date → quarantine + flag |
| `test_seed_accepts_purchase_date_of_today` | "Future" means strictly after today |
| `test_seed_records_orphan_rental_in_quarantine` | The release is recorded, and does **not** flag the item |
| `test_seed_resolves_orphan_rental` | No item is left `In Use` with nobody holding it |
| `test_seed_ignores_semantic_contradiction_in_notes` | Ingestion never reads free text |

`test_importer_reproduces_documented_audit` injects a fixed `today` of
`2026-08-06`, so record 6's defect does not quietly stop being a defect in October
2027.
