// Synthesised rather than fetched (ADR-0018): audio files would be the only fetch
// in the product that is not the API. Off by default, stored beside the theme.
// Never the only signal — every call is paired with a visible one at the call site.

const KEY = 'hardware-hub-sound'

let context = null

export const sound = {
  get enabled() {
    return localStorage.getItem(KEY) === 'on'
  },

  set enabled(on) {
    localStorage.setItem(KEY, on ? 'on' : 'off')
  },

  // ---- six voices, one family (ADR-0018) --------------------------------------
  // Same oscillator, same envelope; only contour and interval change, so the
  // difference a listener notices is the difference that carries the meaning.
  // Flag and resolve are the same tritone, inverted — a problem and its answer.

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

  // ---- the seventh voice, outside the family on purpose (ADR-0018) -------------
  // The six report outcomes; this marks the app posing a question. The synthesis
  // changes — sawtooth glide, opening filter — so it cannot be mistaken for one.

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

      // The opening filter is what reads as *forward* rather than merely up.
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
// synthesis, so the family stays one family.
function play(notes, loudness = 1, hold = 0.16) {
  if (!sound.enabled) return

  try {
    // On first use, not at import: an AudioContext built before a user gesture is
    // a console warning everywhere and a silent failure in some browsers.
    context ??= new (window.AudioContext || window.webkitAudioContext)()
    if (context.state === 'suspended') context.resume()

    for (const [frequency, offset] of notes) {
      const at = context.currentTime + offset
      const oscillator = context.createOscillator()
      const gain = context.createGain()

      oscillator.type = 'triangle'
      oscillator.frequency.setValueAtTime(frequency, at)

      // Shaped rather than clipped — the ramp is what makes 90ms sound intentional.
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
