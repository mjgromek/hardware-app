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

  /** Four voices, one per event. Distinct in pitch and shape, not in volume. */
  rent: () => play([[523.25, 0.0], [659.25, 0.06]], 'triangle'),
  review: () => play([[440.0, 0.0], [554.37, 0.07], [440.0, 0.14]], 'sine'),
  confirmed: () => play([[659.25, 0.0]], 'triangle'),
  refused: () => play([[311.13, 0.0], [233.08, 0.08]], 'sine'),
}

function play(notes, shape) {
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

      oscillator.type = shape
      oscillator.frequency.setValueAtTime(frequency, at)

      // Short, and shaped rather than clipped. A square-edged tone reads as a system
      // error even when it is a success; the ramp is what makes 90ms sound intentional.
      gain.gain.setValueAtTime(0.0001, at)
      gain.gain.exponentialRampToValueAtTime(0.06, at + 0.012)
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.16)

      oscillator.connect(gain).connect(context.destination)
      oscillator.start(at)
      oscillator.stop(at + 0.18)
    }
  } catch {
    // Audio is decoration over a toast that has already been shown. A browser that
    // refuses to make a sound is not a reason for the action to report failure.
  }
}
