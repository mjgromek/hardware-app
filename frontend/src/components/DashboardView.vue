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

/** Type-to-filter: instant, local, and deliberately shallow.
 *
 * **Name and brand only, and that is a security boundary rather than a scope decision.**
 * ADR-0015 keeps the model's filter schema free of any predicate over `notes`, `history`
 * and `review_reason`, because a filter that can *select* on a restricted field leaks it
 * one query at a time — ask for "battery", get the Dell XPS back, and the notes have been
 * read without ever being displayed. A client-side filter over the same fields would be
 * the same oracle with a shorter round trip, and it would be worse: for an admin those
 * fields are actually present in the payload, so it would work.
 *
 * Two columns, listed explicitly. Not `Object.values(item)`, not "everything except the
 * restricted three" — an allow-list, so a field added later is excluded until somebody
 * decides otherwise.
 */
const FILTERABLE = ['name', 'brand']

//: The question the results answer, held so the header can say what is narrowing the
//: table and so typing something new can be told apart from the asked text sitting there.
const asked = ref(null)

const visible = computed(() => {
  // An answer narrows the same table the type-to-filter narrows: one list, one mental
  // model. The AI names rows; the rows themselves stay the table's own — same order,
  // same sort, still intersected by the status chips.
  if (props.searchResults) {
    const chosen = new Set(props.searchResults.items.map((item) => item.id))
    return props.items.filter((item) => chosen.has(item.id))
  }
  // In flight, the text in the bar is a question, not a substring. Narrowing by it
  // emptied the table for the whole call — six seconds of "No hardware matches this
  // filter" as the only response to pressing Enter.
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

// The same rule at mount. This component unmounts on every tab switch while the
// answer lives above it in App state — so returning to the inventory produced an
// empty bar over a table still narrowed by a question nobody could see any more.
// The bar is the source of truth: empty bar, no question, whole table.
onMounted(() => {
  if (props.searchResults) emit('clear-search')
})
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
    <div class="search-field" :class="{ 'is-busy': props.searching }">
      <Icon name="search" class="search-glyph" :size="18" />
      <!-- Not `disabled` while searching. Disabling drops focus to `<body>`, so a
           keyboard user is thrown to the top of the page every time they ask something,
           and a disabled input is unreadable to a screen reader mid-request. `aria-busy`
           says the same thing without taking the control away, and `readonly` stops the
           text changing under an in-flight query. -->
      <input
        v-model="query"
        type="search"
        placeholder="Type to filter, Enter to ask AI…"
        aria-label="Filter the inventory by name or brand, or press Enter to ask AI"
        :aria-busy="props.searching"
        :readonly="props.searching"
      />
      <!-- While the model is thinking the sparkle becomes a spinner: motion exactly
           where the question was typed. The gradient ring alone failed twice over —
           the focus ring sits in its footprint at the same weight (Enter means the
           field is focused, always), and a 2px sweep is below notice anyway. -->
      <Icon v-if="!props.searching" name="sparkle" class="search-spark" :size="18" />
      <span v-else class="search-spinner" aria-hidden="true"></span>
    </div>
    <!-- The gradient outline and the spinner are colour and motion, so they cannot be
         the only signal. Polite, not assertive: the answer is worth interrupting for,
         the wait is not. -->
    <p class="visually-hidden" role="status" aria-live="polite">
      {{ props.searching ? 'Asking AI…' : '' }}
    </p>
    <!-- No submit button: Enter submits, which is what a search field has taught
         everyone to expect, and a button beside a full-width pill was a second target
         for no gain. The form still has `@submit`, so Enter and assistive technology
         both reach it.

         Clear used to live here as well, appearing *inside* this 52px form the instant
         results arrived — it overlapped the bar and read as something popping up over
         the control you had just typed into. It belongs to the results rather than to
         the input, so it now sits in their header beside the mode chip. -->
  </form>

  <div class="panel">
    <div class="panel-head">
      <h2>Hardware</h2>
      <!-- A second surface for results taught two mental models for one list. Instead
           the answer narrows this table, and this header says what is narrowing it:
           the wait, then the question with its provenance and a way out. The mode chip
           is the honesty ADR-0016 requires — a reviewer can tell whether the AI
           answered or the keyword fallback did, from the screen alone. -->
      <span v-if="props.searching" class="chip chip-role">
        Asking AI about “{{ query }}”…
      </span>
      <!-- No Clear button: the search field's own ✕ empties the text, and edited
           text already drops the answer. One control, one behaviour. -->
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
