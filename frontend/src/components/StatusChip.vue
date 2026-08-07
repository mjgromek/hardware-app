<script setup>
import { computed } from 'vue'

// Filled pills, as the wireframe draws them.
//
// Phase 4 tried dot-and-text first, on the argument that a filled pill makes the label
// carry the hue. The wireframe is the reference and it shows pills, so this comes back
// to them — see `docs/WIREFRAME_JUSTIFICATION.md`, where the dots entry is marked
// superseded rather than deleted.
//
// The status enum is exactly Available / In Use / Repair (CONTEXT.md). Only the *label*
// differs: "Rented" and "In Repair" are the wireframe's words and the ones an employee
// says out loud, while the value the API sees is unchanged. One component is where the
// two vocabularies meet, so there is exactly one place to look when they disagree.
const PRESENTATION = {
  Available: { tone: 'chip-ok', label: 'Available' },
  'In Use': { tone: 'chip-busy', label: 'Rented' },
  Repair: { tone: 'chip-stop', label: 'In Repair' },
}

//: `needs_review` is not a status and never becomes one. The enum is fixed at
//: Available | In Use | Repair by the brief, and ADR-0002's whole argument — ingestion
//: judges structure and quarantines what it cannot place — rests on it staying closed.
//: This is the same move "In Use" → "Rented" already makes: a display rule, resolved in
//: the one component where the API's vocabulary meets the employee's.
//: `chip-flag` was written during the visual pass and never rendered by anything — the
//: amber fill and ink are the `!` mark's, already measured at 6.65:1 in ACCESSIBILITY.md,
//: so this reuses a token pair rather than introducing a fourth status colour.
const IN_REVIEW = { tone: 'chip-flag', label: 'In Review' }

const props = defineProps({
  status: { type: String, required: true },
  needsReview: { type: Boolean, default: false },
})

/** In Repair > Rented > In Review > Available.
 *
 * Repair and review are mutually exclusive by construction now (ADR-0003, amended), so
 * the first comparison decides nothing the data can actually present — it is here so the
 * rule reads in full rather than relying on a guard elsewhere to stay correct.
 *
 * Rented outranks In Review because it is the more actionable fact: somebody has the
 * device, and that is who you ask. The flag still blocks the *next* rental, so nothing
 * is lost by showing the holder first — and the amber row marker and the `!` in Actions
 * both remain, so a flagged rented row is never silent about being flagged.
 */
const shown = computed(() => {
  if (props.status === 'Repair') return PRESENTATION.Repair
  if (props.status === 'In Use') return PRESENTATION['In Use']
  if (props.needsReview) return IN_REVIEW
  return PRESENTATION[props.status] ?? { tone: '', label: props.status }
})
</script>

<template>
  <span class="chip chip-status" :class="shown.tone">{{ shown.label }}</span>
</template>
