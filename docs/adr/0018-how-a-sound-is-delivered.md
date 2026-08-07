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

## Amended — six events, and valence carries the meaning

Four events became six: **rent, return, repair, flag, resolve, refusal.** The diff detects
`Repair` and released-from-review transitions alongside the two it already watched.

**One family, varying only contour and interval.** Every voice is the same triangle
oscillator through the same envelope at the same note length. What differs is the *shape* —
which direction the pitch moves and how far. That is the design principle, not a
housekeeping detail: six sounds built from six different syntheses read as six downloaded
noises that happen to share an app, and a listener learns them as arbitrary. Built from one
synthesis, the only thing a listener has to notice is the difference that carries the
meaning.

| Event | Contour | Reads as |
| --- | --- | --- |
| Rent | rising perfect fifth, C5→G5 | bright — you got the thing |
| Return | one note, unmoved, quieter | a completion, not a reward |
| Repair | descending fifth, an octave down, C4→F3 | out of service |
| Flag | rising **tritone**, F4→B4, loudest | dissonant, unresolved, wants a human |
| Resolve | the same tritone descending, B4→F4 | the flag's answer |
| Refusal | one short low note, F3 | blunt — an error, not an alarm |

**Flag and resolve are one gesture, not two sounds.** The flag climbs a tritone and stops
inside it; resolve walks the identical interval back down and lands on the lower, stable
tone. Same two pitches, inverted contour. An admin therefore hears a problem and its answer
as two halves of one thing rather than as "a bad noise" and, later, "a good noise" — which
is the difference between a sound that *means* something and a sound that merely marks that
something happened.

The resolution comes from direction and landing rather than from changing the interval: a
consonant "success" chime would have been easier to write and would have severed the pair.
Flag is the only voice given extra gain, because it is the only one that blocks rentals.

Every voice finishes inside 400 ms — the second note starts at 70 ms and decays over 160.

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
