<script setup>
// The status enum is exactly Available / In Use / Repair (CONTEXT.md). The wireframes
// label these "Available / Rented / In Repair"; the app uses the domain's own words,
// because the API returns them and a UI that renames the enum makes every
// conversation about a bug a translation exercise. See WIREFRAME_JUSTIFICATION.md.
//
// `needs_review` is deliberately NOT a fourth value here. It is orthogonal — a
// flagged item still has a status — so it gets its own column and row marker.
const TONE = {
  Available: 'chip-ok',
  'In Use': 'chip-busy',
  Repair: 'chip-stop',
}

const props = defineProps({ status: { type: String, required: true } })
</script>

<template>
  <span class="chip" :class="TONE[props.status] ?? 'chip-busy'">{{ props.status }}</span>
</template>
