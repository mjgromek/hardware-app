<script setup>
import { computed } from 'vue'

import { displayState } from '../displayState.js'

// Filled pills, as the wireframe draws them. `displayState` owns the enum→label
// translation; this file answers only what colour each state wears.
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
