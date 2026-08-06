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
