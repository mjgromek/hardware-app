# Phase 2 — Rental Engine

Branch `phase-2-rental`. Settled by grilling 2 (`docs/PROMPT_TRAIL.md` Session 9) and
ADR-0007 through ADR-0012, plus the ADR-0003 amendment.

**Sequenced to be cut, not squeezed.** Slice A and B must ship. Slice C is the first thing
to go if the budget bites, and inside C, `My Rentals` goes before `Rent`/`Return`. Cutting
means saying so in the README `⚠️ Partial` section, not shipping it half-built.

Round 3 of the grilling was cut deliberately; its four open questions are settled here.

---

## Slice A — the engine (must ship)

### Schema

`rentals`, in a new `app/rentals.py` (its own `MetaData`, its own `create_schema`, for the
same reason `app/accounts.py` has one — `persist`'s replace semantics must never reach it):

| column | type | notes |
| --- | --- | --- |
| `id` | int PK autoincrement | |
| `item_id` | int, FK → `hardware.id`, not null | |
| `account_id` | int, FK → `users.id`, **nullable** | `NULL` for seed id 7 (ADR-0007) |
| `renter_email` | text, not null | snapshot at rent time |
| `started_at` | datetime, not null | |
| `ended_at` | datetime, **nullable** | `NULL` = active |
| `closed_by_account_id` | int, FK → `users.id`, nullable | |
| `closed_by_email` | text, nullable | |
| `close_kind` | text, nullable | `return` \| `force_return` |

Plus **`CREATE UNIQUE INDEX … ON rentals(item_id) WHERE ended_at IS NULL`** — the partial
index is the thing that makes two active rentals on one item unreachable.

`PRAGMA foreign_keys=ON` via a SQLAlchemy engine event listener in `create_engine_for`.

### Transitions — `app/rentals.py` owns the SQL (ADR-0008)

- `rent(session, item_id, account)` — `UPDATE hardware SET status='In Use' WHERE id=:id AND
  status='Available' AND needs_review=0`, then insert the rental. **Rowcount 0 → the caller
  lost**; raise the guard violation carrying the `In Use` reason.
- `return_(session, item_id, account)` — renter only. Wrong renter → `409`.
- `force_return(session, item_id, admin, reason)` — any active rental, reason mandatory,
  writes `audit_events` (Slice B; in A it may write the rental fields only, with the
  `audit_events` insert added in B).

### Guards — `app/guards.py`

Pure-read pre-checks whose job is the message, not the decision: `Repair`, `In Use`,
`needs_review`, unknown item. One reason per **cause** (ADR-0008), never per timing.

### Retrofits onto shipped Phase 1 routes

- `PATCH /api/hardware/{id}` → refuse `Repair` while the item has an active rental
  (ADR-0009), `409` naming the holder.
- `DELETE /api/hardware/{id}` → refuse while an active rental exists (ADR-0011). A
  *returned* item stays deletable.
- `persist` → refuse outright if any rental row exists (ADR-0011). The README's reseed
  command gains a line saying so.

### Seed id 7

Import creates a rental row with `account_id = NULL`, `renter_email = "j.doe@booksy.com"`,
`started_at` unknown-but-recorded. **Not** a new divergence in `docs/DATA_AUDIT.md` — the
row is imported as the seed states it.

### Routes

`POST /api/hardware/{id}/rent` · `POST /api/hardware/{id}/return` ·
`POST /api/hardware/{id}/force-return` (admin, `{reason}`).

### Tests — Slice A

From `brainstorm.md` §3, plus what the grilling added:

```
test_cannot_rent_hardware_in_repair
test_cannot_rent_flagged_hardware            # ADR-0003 — Dell XPS stays unrentable
test_cannot_rent_hardware_already_in_use
test_cannot_return_hardware_not_rented
test_cannot_return_someone_elses_rental      # the wrong-user guard, absolute
test_rent_then_return_restores_available
test_concurrent_rent_only_one_succeeds       # atomic conditional UPDATE
test_rental_history_records_both_ends
test_admin_force_return_ends_someone_elses_rental
test_cannot_set_repair_on_a_held_item        # retrofit, ADR-0009
test_cannot_delete_a_held_item               # retrofit, ADR-0011
test_reseed_refuses_when_rentals_exist       # retrofit, ADR-0011
test_seed_id_7_imports_as_an_accountless_rental
```

**`test_rental_history_records_both_ends` asserts** (Round 3, settled here): after a
rent→return cycle the `rentals` row has a non-null `started_at` *and* `ended_at`, the
renter fields match who rented, the `closed_by` fields match who returned, and
`close_kind='return'`. One row, not two — the log is the rental, not an event stream.
Its discriminating half is that a second rent→return on the same item produces a **second
row**, so a `UPDATE`-in-place implementation that loses the first cycle fails.

**`test_admin_force_return_ends_someone_elses_rental` is its own test** (Round 3, settled
here) rather than a case inside the wrong-user test: they assert opposite outcomes for the
same request shape, and merging them would make the wrong-user test's name a lie for half
its body.

---

## Slice B — clearing the flag, and who sees what (must ship)

### Schema

`audit_events` (ADR-0010), alongside `rentals`:
`(id, actor_account_id, actor_email, action, item_id, rental_id, reason, created_at)`.
`action` is a closed enum — `force_return`, `clear_review_flag`. `reason` is not null.

### Behaviour

- `POST /api/hardware/{id}/clear-review` — admin only, `{reason}` mandatory. Allowed
  regardless of status. `409` if the item is not flagged. Clears `needs_review` and
  `review_reason`, writes the audit event.
- `force_return` writes its audit event here.
- **Payload restriction (ADR-0012):** `notes`, `history`, `review_reason` are serialised
  for admins only. Renter identity stays visible to every signed-in user. This changes the
  contract table in `tests/conftest.py`.

### Tests — Slice B

```
test_admin_can_clear_needs_review            # ADR-0003
test_cleared_item_becomes_rentable           # the one that matters
test_clearing_an_unflagged_item_is_refused
test_clearing_requires_a_reason
test_non_admin_cannot_clear_needs_review
test_force_return_writes_an_audit_event
test_user_does_not_receive_notes_or_history  # ADR-0012
```

`test_cleared_item_becomes_rentable` is the discriminating one: a flag that clears but
still blocks rental is the decoration ADR-0003 exists to prevent, in a new place.

---

## Slice C — the UI (first to cut)

In cut order, last listed goes first:

1. **`Rent` / `Return` on the dashboard.** A `Rent` button on `Available` unflagged rows; a
   `Return` on rows the signed-in user holds. Refusals surface the `409` reason in the
   existing toast, which already renders guard reasons verbatim.
2. **Force-return and clear-flag in the admin panel.** Both need a reason prompt — a
   dialog, not a `window.confirm`, since a reason has to be typed.
3. **`My Rentals`** (cut first). The wireframe is drawn and `docs/WIREFRAME_JUSTIFICATION.md`
   already records why it was absent in Phase 1. **Payload** (Round 3, settled here): no new
   endpoint — `GET /api/hardware?held_by=me`, one filter on the route the dashboard already
   calls, because a separate `/api/rentals/mine` would duplicate the serialiser that
   ADR-0012 just made role-dependent.

Every deviation continues to go in `docs/WIREFRAME_JUSTIFICATION.md` as it is made.

---

## ADRs Phase 2 writes

Settled in the grilling, written before the code (Round 3's second question):
ADR-0007 the rental record · ADR-0008 atomic claim and refusal vocabulary · ADR-0009 ending
a rental · ADR-0010 audit events · ADR-0011 protecting rental data · ADR-0012 field
visibility · plus an amendment to ADR-0003 for the guard-layer placement.

No further ADR is expected in this phase. One arriving mid-build means something was
decided that the grilling missed — which is worth noticing, not hiding.
