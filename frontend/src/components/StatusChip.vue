<script setup>
import { computed } from 'vue'

import { displayState } from '../displayState.js'

// Filled pills, as the wireframe draws them.
//
// Phase 4 tried dot-and-text first, on the argument that a filled pill makes the label
// carry the hue. The wireframe is the reference and it shows pills, so this comes back
// to them — see `docs/WIREFRAME_JUSTIFICATION.md`, where the dots entry is marked
// superseded rather than deleted.
//
// The status enum is exactly Available / In Use / Repair (CONTEXT.md). Only the *label*
// differs: "Rented" and "In Repair" are the wireframe's words and the ones an employee
// says out loud, while the value the API sees is unchanged. `displayState` now owns that
// translation, because the table's default sort needs the same answer — this file keeps
// only the question it alone can answer, which is what colour each state wears.
//
//: `chip-flag` was written during the visual pass and never rendered by anything — the
//: amber fill and ink are the `!` mark's, already measured at 6.65:1 in ACCESSIBILITY.md,
//: so this reuses a token pair rather than introducing a fourth status colour.
const TONES = {
  Available: 'chip-ok',
  Rented: 'chip-busy',
  'In Repair': 'chip-stop',
  'In Review': 'chip-flag',
}

const props = defineProps({
  status: { type: String, required: true },
  needsReview: { type: Boolean, default: false },
})

//: Resolution lives in `displayState.js`, which the table's default sort reads too — the
//: label a row shows and the group it sorts into come from one function, so they cannot
//: disagree. `PRESENTATION` above still owns the enum→wireframe wording.
const shown = computed(() => {
  const state = displayState({ status: props.status, needs_review: props.needsReview })
  return { tone: TONES[state] ?? '', label: state }
})
</script>

<template>
  <span class="chip chip-status" :class="shown.tone">{{ shown.label }}</span>
</template>
