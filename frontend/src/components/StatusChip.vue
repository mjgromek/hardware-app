<script setup>
// Dot + text, replacing the wireframe's filled pill.
//
// The wireframe fills the whole chip with the status colour, which makes the *label*
// the thing carrying the hue — so the row reads as three coloured blocks and the eye
// has to decode a colour to find "Available". A dot plus the word separates the two
// jobs: the dot is the glanceable signal, the word is the meaning, and the word still
// works in greyscale, in a screenshot, and for anybody who cannot separate red from
// green. See `docs/WIREFRAME_JUSTIFICATION.md`.
//
// The status enum is exactly Available / In Use / Repair (CONTEXT.md). The *label*
// says "Rented" for `In Use` because that is the wireframe's word and the one an
// employee uses out loud; the enum value is unchanged and is what the API sees.
const PRESENTATION = {
  Available: { tone: 'status-available', label: 'Available' },
  'In Use': { tone: 'status-rented', label: 'Rented' },
  Repair: { tone: 'status-repair', label: 'Repair' },
}

const props = defineProps({ status: { type: String, required: true } })
</script>

<template>
  <span class="status" :class="PRESENTATION[props.status]?.tone">
    <span class="status-dot" aria-hidden="true" />
    {{ PRESENTATION[props.status]?.label ?? props.status }}
  </span>
</template>
