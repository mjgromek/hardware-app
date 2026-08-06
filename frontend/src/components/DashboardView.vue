<script setup>
// The dashboard: the whole inventory, filterable by status and sortable by purchase
// date. Both are server-side (`?status=`, `?sort=`) rather than client-side, because
// those query parameters are the tested contract — filtering in the browser would
// leave the endpoint's own filter unexercised by the product that depends on it.
import { computed } from 'vue'

import HardwareTable from './HardwareTable.vue'

const props = defineProps({
  items: { type: Array, required: true },
  status: { type: String, default: null },
  sort: { type: String, default: null },
  counts: { type: Object, required: true },
})

const emit = defineEmits(['filter', 'sort'])

const STATUSES = ['Available', 'In Use', 'Repair']

const flagged = computed(() => props.items.filter((item) => item.needs_review).length)
</script>

<template>
  <h1>Inventory</h1>
  <p class="lede">
    Every item the company owns, with the state it is in right now.
    <template v-if="flagged">
      {{ flagged }} of these need review before they can be rented.
    </template>
  </p>

  <div class="panel">
    <div class="panel-head">
      <h2>Hardware</h2>
      <div class="filters" role="group" aria-label="Filter by status">
        <button
          type="button"
          class="filter-chip"
          :aria-pressed="props.status === null"
          @click="emit('filter', null)"
        >
          All <span class="filter-count">{{ props.counts.total }}</span>
        </button>
        <button
          v-for="value in STATUSES"
          :key="value"
          type="button"
          class="filter-chip"
          :aria-pressed="props.status === value"
          @click="emit('filter', value)"
        >
          {{ value }} <span class="filter-count">{{ props.counts[value] ?? 0 }}</span>
        </button>
      </div>
    </div>

    <HardwareTable :items="props.items" :sort="props.sort" @sort="emit('sort', $event)" />
  </div>
</template>
