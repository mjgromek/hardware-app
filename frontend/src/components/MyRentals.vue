<script setup>
// What this employee is holding. Server-filtered through `?held_by=me` rather than
// filtered in the browser: the filter is scoped by account, and doing it client-side
// would mean shipping every colleague's rental to every colleague to hide it in CSS.
import HardwareTable from './HardwareTable.vue'

const props = defineProps({
  items: { type: Array, required: true },
  currentEmail: { type: String, required: true },
  busyId: { type: [Number, null], default: null },
})

const emit = defineEmits(['return'])
</script>

<template>
  <h1>My rentals</h1>
  <p class="lede">
    Equipment signed out to you. Return it here when you are done with it.
  </p>

  <div class="panel">
    <div class="panel-head">
      <h2>{{ props.items.length }} {{ props.items.length === 1 ? 'item' : 'items' }}</h2>
    </div>

    <div v-if="props.items.length === 0" class="empty">
      You have nothing out. Rent something from the inventory and it will appear here.
    </div>

    <HardwareTable
      v-else
      :items="props.items"
      rentable
      :current-email="props.currentEmail"
      :busy-id="props.busyId"
      @return="emit('return', $event)"
    />
  </div>
</template>
