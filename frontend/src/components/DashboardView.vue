<script setup>
// The dashboard: the whole inventory, filterable by status and sortable by purchase
// date. Both are server-side (`?status=`, `?sort=`) rather than client-side, because
// those query parameters are the tested contract — filtering in the browser would
// leave the endpoint's own filter unexercised by the product that depends on it.
import { computed, ref } from 'vue'

import HardwareTable from './HardwareTable.vue'
import Icon from './Icon.vue'

const props = defineProps({
  items: { type: Array, required: true },
  status: { type: String, default: null },
  sort: { type: String, default: null },
  counts: { type: Object, required: true },
  currentEmail: { type: String, required: true },
  busyId: { type: [Number, null], default: null },
  // `{ mode, items }` or null. The mode is part of the answer, not plumbing: a
  // keyword result presenting itself as the AI is the bug ADR-0016 names.
  searchResults: { type: [Object, null], default: null },
  searching: { type: Boolean, default: false },
})

const emit = defineEmits(['filter', 'sort', 'rent', 'return', 'search', 'clear-search'])

const STATUSES = ['Available', 'In Use', 'Repair']

const flagged = computed(() => props.items.filter((item) => item.needs_review).length)

const query = ref('')

function submitSearch() {
  const asked = query.value.trim()
  if (asked) emit('search', asked)
}

function clearSearch() {
  query.value = ''
  emit('clear-search')
}
</script>

<template>
  <!-- Heading alone, search directly beneath it, as the wireframe has it. The lede
       that used to sit between them is gone: it described what a table of hardware is
       to somebody already looking at one, and it pushed the search box below the fold
       on a laptop. The review count it carried now lives on the nav item, where it is
       a link to the queue rather than a sentence about it. -->
  <h1>Hardware list</h1>

  <form class="panel panel-head search-bar" @submit.prevent="submitSearch">
    <!-- One pill, full width. The visible label is gone and the placeholder carries the
         wireframe's "Ask AI…" — a label above a search field that already says what it
         is for is a second sentence saying the first one again. `aria-label` keeps it
         named for anybody not reading the placeholder. -->
    <div class="search-field">
      <Icon name="search" class="search-glyph" :size="18" />
      <input
        v-model="query"
        type="search"
        placeholder="Ask AI…"
        aria-label="Ask the inventory a question"
        :disabled="props.searching"
      />
      <Icon name="sparkle" class="search-spark" :size="18" />
    </div>
    <!-- No submit button: Enter submits, which is what a search field has taught
         everyone to expect, and a button beside a full-width pill was a second target
         for no gain. The form still has `@submit`, so Enter and assistive technology
         both reach it. Clear stays, but only once there is something to clear. -->
    <button
      v-if="props.searchResults"
      class="button button-quiet"
      type="button"
      style="align-self: flex-end"
      @click="clearSearch"
    >
      Clear
    </button>
  </form>

  <div v-if="props.searchResults" class="panel">
    <div class="panel-head">
      <h2>Search results</h2>
      <!-- The label is the honesty ADR-0016 requires: a reviewer can tell whether
           the AI answered or the keyword fallback did, from the screen alone. -->
      <span class="chip" :class="props.searchResults.mode === 'semantic' ? 'chip-role' : ''">
        {{ props.searchResults.mode === 'semantic'
          ? 'AI search'
          : 'Keyword results — AI search unavailable' }}
      </span>
    </div>
    <p v-if="!props.searchResults.items.length" class="empty">
      Nothing matched. The filter only speaks in name, brand, status and dates — try
      one of those.
    </p>
    <HardwareTable
      v-else
      :items="props.searchResults.items"
      rentable
      :current-email="props.currentEmail"
      :busy-id="props.busyId"
      @rent="emit('rent', $event)"
      @return="emit('return', $event)"
    />
  </div>

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

    <HardwareTable
      :items="props.items"
      :sort="props.sort"
      rentable
      :current-email="props.currentEmail"
      :busy-id="props.busyId"
      @sort="emit('sort', $event)"
      @rent="emit('rent', $event)"
      @return="emit('return', $event)"
    />
  </div>
</template>
