// Four sounds, synthesised rather than fetched.
//
// **No audio files.** The Web Audio API makes these four tones out of an oscillator and
// a gain envelope, which means no binary assets in the repository, no MIME configuration
// on the static mount, nothing added to the bundle, and — the reason that decides it —
// no request. ADR-0001 put the whole app on one origin so there is no cross-origin
// traffic to reason about; shipping four .mp3 files would have been the only fetch in the
// product that is not the API. See ADR-0018.
//
// **Off by default, and stored.** Sound that plays on first visit without being asked for
// is the behaviour every internal tool gets muted for permanently. The preference lives
// in localStorage next to the theme.
//
// **Never the only signal.** Every call here is paired with a toast at the call site.
// A sound that carries information nothing else carries is unusable for anybody who has
// it muted, is deaf, or is wearing one headphone in a meeting.

const KEY = 'hardware-hub-sound'

let context = null

export const sound = {
  get enabled() {
    return localStorage.getItem(KEY) === 'on'
  },

  set enabled(on) {
    localStorage.setItem(KEY, on ? 'on' : 'off')
  },

  // ---- six voices, one family -------------------------------------------------
  //
  // Same oscillator, same envelope, same note length. Only *contour* and *interval*
  // change, so the six read as one product rather than six downloaded noises — and so
  // the difference a listener notices is the difference that carries the meaning.
  //
  // Flag and resolve are a matched pair: the same tritone, inverted. Flag climbs into
  // it and stops there, unresolved; resolve walks the identical interval back down and
  // lands on the lower, stable tone. An admin hears the problem and its answer as two
  // halves of one thing rather than as "a bad noise" and "a good noise". See ADR-0018.

  /** Rising perfect fifth. Bright: you got the thing. */
  rent: () => play([[C5, 0], [G5, 0.07]]),

  /** One note, unmoved, quieter. A completion, not a reward. */
  returned: () => play([[C5, 0]], 0.7),

  /** Descending fifth, an octave down. Out of service. */
  repair: () => play([[C4, 0], [F3, 0.07]]),

  /** Rising tritone, left hanging. Dissonant and the loudest of the six, because this
   *  one blocks rentals and wants a human. */
  flag: () => play([[F4, 0], [B4, 0.07]], 1.25),

  /** The same tritone walked back down. The flag's answer, not a generic success. */
  resolve: () => play([[B4, 0], [F4, 0.07]]),

  /** One short low note. An error, not an alarm — blunt, and over before it annoys. */
  refused: () => play([[F3, 0]], 0.9, 0.09),

  // ---- the seventh voice, outside the family ----------------------------------
  //
  // The six above report outcomes: something in the inventory changed and the sound
  // says how it went. Asking the AI is a different kind of event — the app posing a
  // question, with the answer still ahead — so its sound deliberately breaks the
  // family rules rather than joining as a seventh contour. A sawtooth instead of the
  // triangle, a continuous upward glide instead of two discrete notes, and a filter
  // that opens as the pitch rises: synthetic and forward-moving, the interrogative
  // rise of a question rather than the cadence of a result. A listener who has
  // learned the family hears at once that this is not one of them. See ADR-0018.

  /** A rising glide through an opening filter. The app asking, not reporting. */
  ask: () => {
    if (!sound.enabled) return

    try {
      context ??= new (window.AudioContext || window.webkitAudioContext)()
      if (context.state === 'suspended') context.resume()

      const at = context.currentTime
      const oscillator = context.createOscillator()
      const filter = context.createBiquadFilter()
      const gain = context.createGain()

      oscillator.type = 'sawtooth'
      oscillator.frequency.setValueAtTime(220, at)
      oscillator.frequency.exponentialRampToValueAtTime(880, at + 0.26)

      // The opening filter is what makes it read as *forward* rather than merely up:
      // the sound brightens as it climbs, like something accelerating away. A touch
      // of resonance keeps it unapologetically electronic — this voice has no
      // acoustic pretence to keep.
      filter.type = 'lowpass'
      filter.frequency.setValueAtTime(500, at)
      filter.frequency.exponentialRampToValueAtTime(4000, at + 0.26)
      filter.Q.value = 4

      // Quieter than any outcome: a question should not outrank its answer.
      gain.gain.setValueAtTime(0.0001, at)
      gain.gain.exponentialRampToValueAtTime(0.04, at + 0.03)
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.3)

      oscillator.connect(filter).connect(gain).connect(context.destination)
      oscillator.start(at)
      oscillator.stop(at + 0.32)
    } catch {
      // Same contract as the family: decoration over a visible signal, never load-bearing.
    }
  },
}

// Equal temperament, named so the intervals above are readable as intervals.
const F3 = 174.61
const C4 = 261.63
const F4 = 349.23
const B4 = 493.88
const C5 = 523.25
const G5 = 783.99

// `loudness` scales the shared envelope; `hold` shortens it. Neither changes the
// synthesis — the family stays one family. Every voice finishes inside 400ms:
// the last note starts at 0.07s and decays over 0.16s.
function play(notes, loudness = 1, hold = 0.16) {
  if (!sound.enabled) return

  try {
    // Created on first use, not at import: a suspended AudioContext constructed before a
    // user gesture is a console warning in every browser and a silent failure in some.
    context ??= new (window.AudioContext || window.webkitAudioContext)()
    if (context.state === 'suspended') context.resume()

    for (const [frequency, offset] of notes) {
      const at = context.currentTime + offset
      const oscillator = context.createOscillator()
      const gain = context.createGain()

      oscillator.type = 'triangle' 
      oscillator.frequency.setValueAtTime(frequency, at)

      // Short, and shaped rather than clipped. A square-edged tone reads as a system
      // error even when it is a success; the ramp is what makes 90ms sound intentional.
      gain.gain.setValueAtTime(0.0001, at)
      gain.gain.exponentialRampToValueAtTime(0.06 * loudness, at + 0.012)
      gain.gain.exponentialRampToValueAtTime(0.0001, at + hold)

      oscillator.connect(gain).connect(context.destination)
      oscillator.start(at)
      oscillator.stop(at + hold + 0.02)
    }
  } catch {
    // Audio is decoration over a toast that has already been shown. A browser that
    // refuses to make a sound is not a reason for the action to report failure.
  }
}
