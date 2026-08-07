<script setup>
// The dashboard: the whole inventory, filterable by status and sortable by purchase
// date. Both are server-side (`?status=`, `?sort=`) rather than client-side, because
// those query parameters are the tested contract — filtering in the browser would
// leave the endpoint's own filter unexercised by the product that depends on it.
import { computed, onMounted, ref, watch } from 'vue'

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

const query = ref('')

/** Type-to-filter: name and brand only, and that is a security boundary — a
 * client-side filter over `notes` would be ADR-0015's oracle with a shorter round
 * trip. An allow-list, so a field added later is excluded until somebody decides. */
const FILTERABLE = ['name', 'brand']

//: The question the results answer, so new typing can be told apart from it.
const asked = ref(null)

const visible = computed(() => {
  // An answer narrows the same table the type-to-filter narrows: one list, one
  // mental model. The AI names rows; the rows stay the table's own.
  if (props.searchResults) {
    const chosen = new Set(props.searchResults.items.map((item) => item.id))
    return props.items.filter((item) => chosen.has(item.id))
  }
  // In flight the bar's text is a question, not a substring — narrowing by it
  // emptied the table for the whole call.
  if (props.searching) return props.items
  const needle = query.value.trim().toLowerCase()
  if (!needle) return props.items
  return props.items.filter((item) =>
    FILTERABLE.some((field) => (item[field] ?? '').toLowerCase().includes(needle)),
  )
})

//: Enter is the only thing that reaches the model. Typing costs nothing and calls
//: nothing; asking is a deliberate act, which is also what makes the latency acceptable.
function submitSearch() {
  const question = query.value.trim()
  if (!question) return
  asked.value = question
  emit('search', question)
}

function clearSearch() {
  query.value = ''
  asked.value = null
  emit('clear-search')
}

// Editing the text after an answer means the answer no longer describes the bar:
// drop the results and let the keystroke filter, rather than filtering inside a
// stale answer nobody asked to keep.
watch(query, (text) => {
  if (props.searchResults && text !== asked.value) {
    asked.value = null
    emit('clear-search')
  }
})

// The same rule at mount: this component unmounts per tab switch while the answer
// lives above it in App state — returning showed an empty bar over a table still
// narrowed by a question nobody could see. Empty bar, no question, whole table.
onMounted(() => {
  if (props.searchResults) emit('clear-search')
})
</script>

<template>
  <h1>Hardware list</h1>

  <form class="panel panel-head search-bar" @submit.prevent="submitSearch">
    <div class="search-field" :class="{ 'is-busy': props.searching }">
      <Icon name="search" class="search-glyph" :size="18" />
      <!-- `readonly`, never `disabled`, while searching: disabling drops focus to
           `<body>` and is unreadable to a screen reader mid-request. -->
      <input
        v-model="query"
        type="search"
        placeholder="Type to filter, Enter to ask AI…"
        aria-label="Filter the inventory by name or brand, or press Enter to ask AI"
        :aria-busy="props.searching"
        :readonly="props.searching"
      />
      <!-- The sparkle becomes a spinner in flight: the gradient ring cannot carry
           the state — Enter means the field is focused, and the focus ring sits in
           its exact footprint. -->
      <Icon v-if="!props.searching" name="sparkle" class="search-spark" :size="18" />
      <span v-else class="search-spinner" aria-hidden="true"></span>
    </div>
    <!-- Colour and motion cannot be the only signal. Polite: the answer is worth
         interrupting for, the wait is not. -->
    <p class="visually-hidden" role="status" aria-live="polite">
      {{ props.searching ? 'Asking AI…' : '' }}
    </p>
  </form>

  <div class="panel">
    <div class="panel-head">
      <h2>Hardware</h2>
      <!-- The header says what is narrowing the table: the wait, then the question
           with its provenance. The mode chip is ADR-0016's honesty — which path
           answered, from the screen alone. No Clear button: the field's own ✕
           empties the text, and edited text already drops the answer. -->
      <span v-if="props.searching" class="chip chip-role">
        Asking AI about “{{ query }}”…
      </span>
      <span
        v-else-if="props.searchResults"
        class="chip"
        :class="props.searchResults.mode === 'semantic' ? 'chip-role' : ''"
      >
        {{ props.searchResults.mode === 'semantic'
          ? `AI search — “${asked}”`
          : `Keyword results for “${asked}” — AI search unavailable` }}
      </span>
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
      :items="visible"
      :sort="props.sort"
      rentable
      :current-email="props.currentEmail"
      :busy-id="props.busyId"
      :empty-text="props.searchResults
        ? 'Nothing matched. The filter only speaks in name, brand, status and dates — try one of those.'
        : 'No hardware matches this filter.'"
      @sort="emit('sort', $event)"
      @rent="emit('rent', $event)"
      @return="emit('return', $event)"
    />
  </div>
</template>
