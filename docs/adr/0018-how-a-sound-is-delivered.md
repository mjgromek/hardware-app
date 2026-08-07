# ADR-0018 — How a sound is delivered

- **Status:** Accepted
- **Date:** 2026-08-07
- **Source:** Phase 4 — four notification events over the existing toast layer

## Context

Four events earn a sound: an admin learning somebody rented an item, an admin learning an
item entered review, anybody's own action being confirmed, and any `409` refusal. Three
delivery questions follow, and only the first is obvious.

## Decision

**Synthesised, not fetched.** Four tones built from a Web Audio oscillator and a gain
envelope. No `.mp3` in the repository, nothing added to the bundle, no MIME configuration
on the static mount, and no request — ADR-0001 put the whole app on one origin precisely so
there is no traffic to reason about beyond the API, and four audio files would have been
the only fetch in the product that is not one.

**Off by default, stored beside the theme.** Sound that plays unasked on first visit is
what an internal tool gets muted for permanently.

**Remote events are derived by diffing snapshots, not pushed.** Two of the four are about
somebody *else's* action, and there is no websocket or SSE. The client compares each
inventory fetch with the previous one: an item that was not `In Use` and now is, or was not
flagged and now is, raises the event. So an admin hears these **the next time their client
refetches** — after any action they take — rather than the moment they happen.

**Every sound is paired with a toast at its call site.** No sound carries information
nothing else carries.

## Consequences

- **This is notification on refresh, not realtime, and the phrase matters.** An admin
  sitting on an idle dashboard hears nothing until something makes their client fetch.
  Calling it "notifications" without that qualifier would oversell it; adding polling to
  close the gap would put a timer on every client to serve four sounds.
- The confirmed-action tone doubles as the toggle's own feedback: switching sound on plays
  it once, so "on" is audible rather than a claim the UI makes about itself.
- An admin renting an item hears the confirmation tone, not the rent tone — the diff
  excludes rows the admin took themselves, or the same action would announce twice.
- **`prefers-reduced-motion` governs the toast animation, not the sound**, and conflating
  them would be wrong. That setting says a person is affected by movement; it says nothing
  about whether they want audio, and treating it as a proxy for "no feedback" would silently
  remove a channel from people who asked about a different one. Sound is governed by its
  own explicit opt-in, which is the only preference that actually expresses the choice.
- **Trade-off accepted:** the frontend still has no tests, so these four events are
  verified by using them rather than by a suite. Consistent with the documented shortcut,
  and it is the largest untested surface in the project (`BACKLOG.md`).
