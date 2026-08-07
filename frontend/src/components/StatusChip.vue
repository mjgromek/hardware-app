<script setup>
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

const props = defineProps({ status: { type: String, required: true } })
</script>

<template>
  <span class="chip chip-status" :class="PRESENTATION[props.status]?.tone">
    {{ PRESENTATION[props.status]?.label ?? props.status }}
  </span>
</template>
