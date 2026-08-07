# Wireframe Justification

Every place the built UI departs from the wireframes supplied with the brief, with
the reason, recorded as the deviation is made rather than reconstructed afterwards.

## Why there are no images here

The wireframes are Booksy's material and the brief marks them confidential. This
repository is public, so they are **deliberately not committed** —
`docs/wireframes/` is gitignored and the files stay on the local machine only.

That constraint shapes this document. Because a reader cannot open the wireframe
next to the deviation, **each entry describes the original in prose** before saying
what changed: what the wireframe showed, what was built instead, and why. The
document is meant to stand alone and be judged on its own, without the images.

Where a wireframe was followed as drawn, there is no entry. Silence means no
deviation, not an undocumented one.

## Deviations

Grouped by what drove them: the domain's own vocabulary, fields that do not exist,
controls that would fail, and phases that have not happened yet.

### Table — status labels are the enum's words, not the wireframe's

> **Superseded in Phase 4** by *"Rented" is the label; `In Use` is still the value*
> below. The reasoning here — that renaming the enum makes every bug report a
> translation exercise — still holds and is why the *value* never changed; Phase 4
> separated the display label from it rather than choosing one word for both. Left in
> place because the reversal is the record.


**The wireframe showed:** three status chips reading `Available`, `Rented`,
`In Repair` — black, grey and red respectively.
**What was built:** the same three chips with the same three tones, labelled
`Available`, `In Use`, `Repair`.
**Why:** the status enum is exactly `Available | In Use | Repair` (`CONTEXT.md`, and a
`CLAUDE.md` non-negotiable). The API returns those strings, the guards match on them,
and every test names them. A UI that renames the enum makes every conversation about a
bug a translation exercise — "the rented one" and "the In Use one" would be the same
item with two names. The tones are kept because they are the useful half of the
wireframe's decision: the default state carries the strongest fill, so an admin
scanning for what can be issued finds it without reading.

### Table — "Date Added" became "Purchase date"

**The wireframe showed:** a `Date Added` column.
**What was built:** `Purchase date`.
**Why:** the field is `purchase_date`, and it comes from the seed as the date the
company bought the device. Nothing in the data records when a row was added. "Date
Added" would be a label making a claim the column cannot support, and the one row with
no date (seed id 10) would then read as "added at an unknown time" rather than "we do
not know when this was bought".

### Table and Add-device form — no Serial Number, no Category

**The wireframe showed:** a `Serial Number` column in the admin table, and a
`Category` select in the Add New Device modal.
**What was built:** neither.
**Why:** no such fields exist. The seed's records carry name, brand, purchase date,
status, notes, history and assignee, and `docs/DATA_AUDIT.md` is written against
exactly that shape. Adding two columns to satisfy a wireframe would mean a schema
change, a migration on the deployed volume, and eleven rows with both fields empty —
a column that is blank for every item is worse than an absent one, because it looks
like data loss. Recorded in `BACKLOG.md` as the fields to add if the domain gains them.

### Admin table — no edit (pencil) action

**The wireframe showed:** three row actions — edit, repair, delete.
**What was built:** two — repair and delete.
**Why:** there is no endpoint that changes an item's name, brand or date. The
wireframe's own edit button is honest about this: clicking it raises a toast reading
"Edit functionality for MacBook Pro 16"". Shipping a control whose only behaviour is
to admit it does nothing is worse than shipping the two that work, and inventing a
`PATCH` for arbitrary fields would be production code with no failing test behind it.

### Dashboard — no "Ask AI…" bar, and no Rent action

**The wireframe showed:** a search field reading `Ask AI…` above the table with a
sparkle affordance, a `Rent` button on every row, a `My Rentals` nav entry, and a
"Rental request submitted" confirmation.
**What was built:** none of them.
**Why:** semantic search is Phase 3 and the rental engine is Phase 2. A `Rent` button
in a build with no rental engine is a lie a reviewer can click, and the flagged rows
make that concrete: ADR-0003 says a flagged item cannot be rented, and there is no
guard yet to refuse the request. The filter chips take the space the AI bar occupied,
because filtering is what this phase can actually do.

### Login — no client-side company-domain rule

**The wireframe showed:** the email field labelled "Email (company domain only)" with
placeholder `name@booksy.com`, and an error state reading "Invalid domain. Please use
@booksy.com".
**What was built:** a plain email field, the same placeholder as a hint, and no
domain check.
**Why:** two reasons, and the first is fatal on its own. The only account that exists
on a fresh deployment is bootstrapped from `ADMIN_EMAIL` (ADR-0005), and on the
Railway instance that address is `admin@hardwarehub.internal` — a client-side
`@booksy.com` rule would lock the only admin out of the only screen they can reach.
Second, the rule leaks: the API deliberately answers every bad credential identically
so the login form cannot be used to enumerate accounts, and a browser-side check that
says "wrong domain" hands back exactly the fact the server refuses to confirm.

### Login — different headline

**The wireframe showed:** "Welcome back / Sign in to your account".
**What was built:** "Hardware Hub / Sign in to manage company equipment".
**Why:** the login screen is the only place the product names itself — the sidebar
that carries the brand everywhere else is behind the session. "Welcome back" also
addresses a returning user, and on an internal tool seeded with one admin account the
first visit is nobody's second.

### Sidebar — "Hardware Hub", not "Hardware Manager"

**The wireframe showed:** `Hardware Manager` beside the mark.
**What was built:** `Hardware Hub`.
**Why:** that is the product's name in the brief, the repository, the page title and
every document. One name.

### Added: a Needs review screen, and a row marker for the flag

**The wireframe showed:** nothing for `needs_review`. Three statuses, no fourth state,
no queue.
**What was built:** a `Needs review` nav entry with a count, a screen listing every
flagged item with the reason ingestion recorded, an amber `Needs review` chip in its
own column, and an amber edge marker on the flagged row.
**Why:** ADR-0003 makes the flag a rentability guard, so a flagged item is inventory
nobody can issue — invisible, that is stock that has silently disappeared. It is
**not** a fourth status chip because it is not a status: a flagged item still has one
(both flagged seed rows are `Available`). Two orthogonal facts cannot share one cell,
so the flag marks the whole row from the edge and states itself in words in its own
column. The edge marker is what makes it scannable down a dense table without reading
every line.

**The screen is read-only, and that is a gap rather than a decision.** Nothing in the
API clears the flag — ADR-0003 records it as an unresolved consequence — so the screen
says so in plain words instead of offering a button that would fail. Tracked in
`BACKLOG.md` as due before the Phase 1 gate.

### Sign out is client-side only

**The wireframe showed:** a red `Logout` at the foot of the sidebar.
**What was built:** the same control, labelled `Sign out`, which clears the client's
state and returns to the login screen — and says so in its confirmation.
**Why:** there is no logout route. The session is a signed cookie with no server-side
record (`app/sessions.py`), so there is nothing to invalidate; the honest thing is a
control that describes what it did rather than one implying the session was revoked.
In `BACKLOG.md`, pointed at `/security-review`.

## Phase 2 — the rental verbs

### Dashboard — a blocked row states its reason instead of showing a dead button

**The wireframe showed:** a `Rent` button on every row, greyed out on `Rented` and
`In Repair` ones.
**What was built:** `Rent` on rentable rows, `Return` on rows you hold, and on the rest a
short line of text — "In Repair", "Somebody else has it", "Needs review before it can be
rented".
**Why:** three different facts. A greyed button says "not now" and makes you hover to
learn why; the row already knows the answer, so it says it. This is also the brief's own
requirement that a `409` show its readable reason, applied one step earlier — the reason
is visible before the click, and the server's own message still arrives in a toast when a
row goes stale between paint and click.

### Dashboard — who holds an item, beside the status

**The wireframe showed:** a `Status` column with no holder.
**What was built:** the renter's address beside the `In Use` chip, reading "you" when it is
yours.
**Why:** ADR-0012. The point of `In Use` on an internal tool is knowing who to ask, and
without it the dashboard sends that question to Slack where the tool cannot see it.

### Renting is immediate, so the confirmation says so

**The wireframe showed:** a toast reading "Rental request submitted for MacBook Pro 16"".
**What was built:** "Apple iPhone 13 Pro Max is yours".
**Why:** "request submitted" describes an approval workflow, and there isn't one — the
rental is a single atomic claim that has already succeeded by the time the toast appears
(ADR-0008). Copy that implies a pending approval would have people waiting for an email.

### My rentals — the empty state invites the action

**The wireframe showed:** "You don't have any active rentals".
**What was built:** "You have nothing out. Rent something from the inventory and it will
appear here."
**Why:** an empty screen is the one place a person is most likely to be stuck, and the
wireframe's version reports a fact without saying what to do about it.

### Added: force-return and clear-flag, both behind a reason

**The wireframe showed:** neither. Its admin row actions are edit, repair, delete.
**What was built:** a recall action on held rows and a clear-flag action on flagged rows,
each opening the same dialog with a mandatory reason field.
**Why:** ADR-0009 and ADR-0010 — an admin ending somebody else's rental or releasing a
flagged item is an override, and the reason is what a later incident interrogates. One
dialog rather than two because they are the same kind of event; the field is `required`
client-side because the server rejects an empty reason and a client that lets you submit
one just turns a considered refusal into a `422`.

---

## Phase 3 — the AI surfaces

### The "Ask AI…" bar arrives, labelled with which path answered

**The wireframe showed:** a search field reading `Ask AI…` with a sparkle affordance.
**What was built:** the search field, above the inventory table where the wireframe put
it — with a visible mode chip the wireframe never had: "AI search" when the model
answered, "Keyword results — AI search unavailable" when it degraded (ADR-0016).
**Why the deviation:** the wireframe's bar makes no claim about what happens when the
provider is down, and a fallback that looks identical to the primary makes the README's
"graceful fallback" unverifiable from the screen. Honesty is a feature; the chip is the
feature. The Phase 1 justification for the bar's absence is above and is now closed.

### Added: the Inventory Auditor panel

**The wireframe showed:** nothing — no auditor surface exists in the wireframes.
**What was built:** an admin-panel section with a Run audit button, the findings as a
table (kind, evidence, explanation), and a "Flag for review" action per finding that
opens the existing reason dialog *prefilled from the finding but editable* (ADR-0017).
**Why:** ADR-0014 makes findings a computed payload an admin acts on; a surface had to
exist for the acting, and the admin panel is where every other override lives. The
prefill is a convenience; the edit is the point — the recorded reason is the human's
claim, not the model's.

## Phase 4 — the visual finish pass

Structure follows the wireframe throughout; everything below is finish. Each entry says
what the wireframe showed before saying what was built, because the images are not in
this repository and the document has to stand without them.

### Status pills became a dot and a word

> **Superseded later in Phase 4 — reverted to pills.** The wireframe is the reference and
> it draws pills; we came back to them, with a fixed width and per-theme fills. The
> argument below is still the honest reason the detour happened and is left in place
> rather than deleted. What survived it: the *label* is still separated from the *value*
> (see the entry below), and each tone still carries a light and a dark stop — the
> problem the dots were reaching for was real even though the shape was not the answer.


**The wireframe showed:** a filled pill per status — black `Available`, grey `Rented`,
red `In Repair` — the whole chip carrying the status colour with the label reversed out
of it.
**What was built:** an 8px dot in the status hue followed by the word in ordinary body
ink. Green `Available`, blue `Rented`, red `Repair`.
**Why:** the pill makes the *label* the thing carrying the hue, so a row reads as three
coloured blocks and the eye has to decode a colour to find the word inside it. Splitting
them gives each job one element: the dot is the glanceable signal, the word is the
meaning. The word still works in greyscale, in a screenshot, and for anyone who cannot
separate red from green — which the pill's reversed-out label does not, because there the
colour *is* the background the text depends on for contrast. Each hue carries two stops
so the dot stays distinguishable on a dark surface without changing hue.

Measured rather than eyeballed: every dot clears the 3:1 non-text threshold in both themes
(3.30–5.17:1 light, 6.42–10.19:1 dark), and the amber `!` beside the red Repair dot does
**not** separate on luminance — 1.52:1 light, 1.82:1 dark. It is safe because colour is
never the only signal, which is the argument and the numbers in
[`docs/ACCESSIBILITY.md`](ACCESSIBILITY.md).

### "Rented" is the label; `In Use` is still the value

**The wireframe showed:** `Rented`.
**What was built:** `Rented` on screen, over an enum whose value is unchanged.
**Why:** the status enum is exactly `Available | In Use | Repair` (`CONTEXT.md`, and a
`CLAUDE.md` non-negotiable) — it is what the API returns, what the guards match on, and
what every test names. But `Rented` is the wireframe's word and the one an employee says
out loud. Phase 1 resolved this tension by showing the enum's word everywhere; Phase 4
splits presentation from value instead, which is the smaller lie: the label is a
rendering choice, and renaming the enum would have made every bug report a translation
exercise. The mapping lives in one component (`StatusChip.vue`) so there is exactly one
place where the two vocabularies meet.

### An amber `!` replaces the Rent button on flagged rows

**The wireframe showed:** a `Rent` button on every row, greyed out where the item cannot
be taken.
**What was built:** on a flagged row, an amber `!` where the button would be, with the
review reason in a tooltip on hover *and* on keyboard focus.
**Why:** a greyed button says "not now" and makes you hover to learn why. A flagged item
is not temporarily unavailable — it is *under review*, which is a different fact, and the
row already knows the reason. Phase 2 rendered that reason as inline text; the wireframe's
actions column is too narrow for a sentence, so the mark carries it in a tooltip and an
`aria-label` instead. It is `tabindex="0"` deliberately: the tooltip is the only place the
reason appears in this table, so a keyboard user who could not open it could not find out
why the item is blocked.

### The heading stands alone, with search directly beneath

**The wireframe showed:** the page title, then the search field.
**What was built:** the same, after removing a paragraph that had grown between them.
**Why:** the lede described what a table of hardware is to somebody already looking at
one, and it pushed the search box toward the fold on a laptop. The one piece of live
information it carried — how many items need review — now sits on the `Needs review` nav
item as a count, where it is a link to the queue rather than a sentence about it.

### The holder is shown, though the wireframe omits it

**The wireframe showed:** a `Status` column with no holder — `Rented` and nothing else.
**What was built:** the renter's address beside the `Rented` dot, reading "you" when it is
yours. Visible to every signed-in account, not just admins.
**Why:** this is the deviation with an argument rather than an oversight, and it was
re-examined in Phase 4 before being kept. ADR-0012 decided it deliberately: the point of
`In Use` on an internal tool is knowing who to ask for the headphones, and hiding it moves
that conversation to Slack where the tool cannot see it. Hiding it from non-admins was
considered and dropped — the server would have had to stop serialising `assigned_to` for
`user` accounts, which contradicts ADR-0012 and turns
`test_renter_identity_is_visible_to_every_signed_in_user` red; and hiding it in the UI
while still shipping the address in the JSON would be an appearance of privacy rather than
privacy. Either the field is theirs to see or it is not, and ADR-0012 says it is.

### The Review column is gone from every table but the queue

**The wireframe showed:** no Review column anywhere — three statuses and no fourth state.
**What was built:** Phase 1 added one to every table; Phase 4 removes it from all of them
except the needs-review tab, where it is the subject.
**Why:** the amber `!` in the Actions column already marks a flagged row, carries the
reason in its tooltip, and is the thing that replaces the Rent button — so a Review column
beside it repeated the same fact in the same row twice. On the needs-review screen the
column stays, because there the reason *is* the content rather than an annotation on it.

### "Somebody else has it" is gone

**The wireframe showed:** a greyed `Rent` button on rows that cannot be taken.
**What was built:** nothing in the Actions column for a rented row.
**Why:** the Status pill one cell to the left already says `Rented`. Repeating it as
"somebody else has it" told the reader nothing new and made the Actions column a second
status column. A refusal still states its cause — the `409` carries the server's own
reason, which is the case where the reader genuinely does not already know.

### The search field is a pill with no visible label

**The wireframe showed:** a full-width search bar reading `Ask AI…`, a magnifier at the
left and a sparkle at the right.
**What was built:** the same, with the visible "Ask the inventory" label removed and kept
as an `aria-label`.
**Why:** a label above a field whose placeholder already says what it is for is a second
sentence saying the first one again. The subtle fill rather than a hard border is what
makes it read as a place to ask a question rather than as a form input — which matters,
because "Ask AI" is a different promise from "filter".

### A row that cannot be rented shows nothing in Actions

**The wireframe showed:** a greyed-out `Rent` button on rows that cannot be taken.
**What was built:** an empty Actions cell. No button, no label.
**Why:** the same argument that removed "somebody else has it", applied to the last case
left. The Status pill one cell to the left already says `In Repair`, so a label repeating
it made Actions a second status column — and a greyed button implies a control that might
become available to *this* reader, which for a non-admin it never will. The absence of the
button is the signal, and the pill is the reason. A refused attempt still states its cause:
the `409` carries the server's own words, which is the one case where the reader genuinely
does not already know.

Note what this does **not** remove: the Repair toggle itself, which lives in the admin
table as a wrench glyph labelled `Send {name} to Repair` / `Release {name} from Repair` —
already an action rather than a state, and untouched.
