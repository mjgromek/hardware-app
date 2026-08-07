<script setup>
// The dense table. This is the product's primary surface, so it is the one component
// that gets real keyboard behaviour: a roving tabindex over the rows, arrows to move,
// Home/End to jump. One Tab press enters the table and the arrows take over, instead
// of Tab walking through every action button in every row.
import { computed, nextTick, ref, watch } from 'vue'
import Icon from './Icon.vue'
import StatusChip from './StatusChip.vue'

const props = defineProps({
  items: { type: Array, required: true },
  //: The signed-in account's email, so a row can tell "yours" from "somebody's".
  //: Renter identity is visible to everyone (ADR-0012), which is what makes this
  //: possible without a second request.
  currentEmail: { type: String, default: '' },
  //: Rent / Return live on the dashboard. Off for the admin table, which has its own
  //: verbs and would otherwise offer two ways to move one item.
  rentable: { type: Boolean, default: false },
  // Admin columns and row actions. A plain user sees the same inventory and none of
  // the controls — the server refuses them anyway (403), so this only avoids
  // offering an action that cannot succeed.
  manage: { type: Boolean, default: false },
  sort: { type: String, default: null },
  busyId: { type: [Number, null], default: null },
})

const emit = defineEmits(['sort', 'toggle-repair', 'delete', 'rent', 'return', 'force-return'])

//: Why this row cannot be rented, in the words the API would use. Shown *before* the
//: click rather than only after it: the reason is already in the row, and making
//: somebody press a button to be told "it is in Repair" is a worse version of knowing.
//: A 409 can still arrive — the row can go stale between paint and click — and the
//: toast carries the server's own reason when it does.
function heldByMe(item) {
  return item.status === 'In Use' && item.assigned_to === props.currentEmail
}

const rows = ref([])
const focusIndex = ref(0)

// Keep the focused row in range when the list shrinks under it — a delete or a
// filter change must not leave the roving tabindex pointing past the end.
watch(
  () => props.items.length,
  (length) => {
    if (focusIndex.value > length - 1) focusIndex.value = Math.max(0, length - 1)
  },
)

const flaggedCount = computed(() => props.items.filter((item) => item.needs_review).length)

// Sorting is local to the table, and all three columns use one mechanism.
//
// The API sorts by `purchase_date` only, in one direction (`SortKey` has a single
// member and no `order`). Name and brand ascending *and* descending would mean four
// new server behaviours and the tests to pin them; at eleven rows the browser can do
// it for free and the two mechanisms would otherwise disagree about which one owns
// order. Recorded in BACKLOG.md — the server parameter is now unused by this screen.
const SORTABLE = {
  name: (item) => (item.name ?? '').toLowerCase(),
  brand: (item) => (item.brand ?? '').toLowerCase(),
  purchase_date: (item) => item.purchase_date ?? '',
  date_added: (item) => item.date_added ?? '',
}

const sortKey = ref(null)
const sortAscending = ref(true)

function toggleSort(key) {
  if (sortKey.value === key) {
    sortAscending.value = !sortAscending.value
  } else {
    sortKey.value = key
    sortAscending.value = true
  }
}

const sorted = computed(() => {
  const rows = [...props.items]
  if (!sortKey.value) return rows
  const read = SORTABLE[sortKey.value]
  const direction = sortAscending.value ? 1 : -1
  return rows.sort((a, b) => {
    const left = read(a)
    const right = read(b)
    // Missing values sort last in both directions rather than flipping to the top on
    // a descending click — seed id 10 has no brand and no date, and an empty string
    // sorting first would put the one unidentifiable row above everything twice.
    if (left === '' && right !== '') return 1
    if (right === '' && left !== '') return -1
    if (left < right) return -1 * direction
    if (left > right) return 1 * direction
    return 0
  })
})

function ariaSort(key) {
  if (sortKey.value !== key) return 'none'
  return sortAscending.value ? 'ascending' : 'descending'
}

function sortGlyph(key) {
  if (sortKey.value !== key) return '↕'
  return sortAscending.value ? '↑' : '↓'
}

function move(delta, event) {
  const last = props.items.length - 1
  if (last < 0) return
  event.preventDefault()
  focusIndex.value = Math.min(last, Math.max(0, focusIndex.value + delta))
  focusRow()
}

function jump(index, event) {
  if (props.items.length === 0) return
  event.preventDefault()
  focusIndex.value = index < 0 ? props.items.length - 1 : 0
  focusRow()
}

async function focusRow() {
  await nextTick()
  rows.value[focusIndex.value]?.focus()
}

function onKeydown(event) {
  if (event.key === 'ArrowDown') move(1, event)
  else if (event.key === 'ArrowUp') move(-1, event)
  else if (event.key === 'Home') jump(0, event)
  else if (event.key === 'End') jump(-1, event)
}

// `-` rather than an empty cell: the seed has a row with no brand and no purchase
// date (id 10), and a blank cell reads as a rendering bug rather than as missing data.
function shown(value) {
  return value === null || value === undefined || value === '' ? null : value
}
</script>

<template>
  <div class="table-scroll">
    <table>
      <caption class="sr-only">
        Hardware inventory, {{ props.items.length }} items,
        {{ flaggedCount }} needing review. Use the arrow keys to move between rows.
      </caption>
      <thead>
        <tr>
          <th scope="col" :aria-sort="ariaSort('name')">
            <button type="button" class="sort-button" @click="toggleSort('name')">
              Name <span class="sort-arrow">{{ sortGlyph('name') }}</span>
            </button>
          </th>
          <th scope="col" :aria-sort="ariaSort('brand')">
            <button type="button" class="sort-button" @click="toggleSort('brand')">
              Brand <span class="sort-arrow">{{ sortGlyph('brand') }}</span>
            </button>
          </th>
          <th scope="col" class="col-date" :aria-sort="ariaSort('purchase_date')">
            <button type="button" class="sort-button" @click="toggleSort('purchase_date')">
              Purchase date <span class="sort-arrow">{{ sortGlyph('purchase_date') }}</span>
            </button>
          </th>
          <th scope="col"><span class="th-label">Status</span></th>
          <th v-if="props.manage || props.rentable" scope="col">
            <span class="th-label" style="justify-content: flex-end">Actions</span>
          </th>
        </tr>
      </thead>

      <tbody @keydown="onKeydown">
        <tr
          v-for="(item, index) in sorted"
          :key="item.id"
          ref="rows"
          :tabindex="index === focusIndex ? 0 : -1"
          :class="{ 'is-flagged': item.needs_review }"
          @focus="focusIndex = index"
        >
          <td class="cell-name">{{ item.name }}</td>
          <td>
            <span v-if="shown(item.brand)">{{ item.brand }}</span>
            <span v-else class="missing" title="No brand recorded">—</span>
          </td>
          <td class="cell-date">
            <span v-if="shown(item.purchase_date)">{{ item.purchase_date }}</span>
            <span v-else class="missing" title="No purchase date recorded">—</span>
          </td>
          <td>
            <StatusChip :status="item.status" />
            <span v-if="item.status === 'In Use'" class="held-by">
              {{ heldByMe(item) ? 'you' : item.assigned_to || 'unknown holder' }}
            </span>
          </td>
          <td v-if="props.rentable" class="cell-actions">
            <button
              v-if="heldByMe(item)"
              type="button"
              class="button button-quiet"
              :disabled="props.busyId === item.id"
              @click="emit('return', item)"
            >
              Return
            </button>
            <template v-else-if="item.needs_review">
              <span class="flag-holder">
                <span
                  class="flag-mark"
                  tabindex="0"
                  role="img"
                  :aria-label="`Needs review: ${item.review_reason || 'the record could not be verified at import'}`"
                >!</span>
                <span class="flag-tip" role="tooltip">
                  {{ item.review_reason || 'The record could not be verified at import.' }}
                </span>
              </span>
            </template>
            <!-- A row that cannot be rented shows nothing here. The Status pill one cell
                 left already says "In Repair" or "Rented", and the absence of the button
                 is itself the signal — a label repeating the pill made Actions a second
                 status column. A refused attempt still states its cause: the 409 carries
                 the server's own reason, which is the case where the reader genuinely
                 does not already know. -->
            <button
              v-else-if="item.status === 'Available'"
              type="button"
              class="button"
              :disabled="props.busyId === item.id"
              @click="emit('rent', item)"
            >
              Rent
            </button>
          </td>

          <td v-else-if="props.manage" class="cell-actions">
            <button
              v-if="item.status === 'In Use'"
              type="button"
              class="icon-button"
              :disabled="props.busyId === item.id"
              :title="`Recall ${item.name} from ${item.assigned_to}`"
              :aria-label="`Recall ${item.name} from ${item.assigned_to}`"
              @click="emit('force-return', item)"
            >
              <Icon name="out" />
            </button>
            <button
              type="button"
              class="icon-button"
              :disabled="props.busyId === item.id"
              :title="
                item.status === 'Repair'
                  ? `Release ${item.name} from Repair`
                  : `Send ${item.name} to Repair`
              "
              :aria-label="
                item.status === 'Repair'
                  ? `Release ${item.name} from Repair`
                  : `Send ${item.name} to Repair`
              "
              @click="emit('toggle-repair', item)"
            >
              <Icon name="wrench" />
            </button>
            <button
              type="button"
              class="icon-button is-danger"
              :disabled="props.busyId === item.id"
              :title="`Delete ${item.name}`"
              :aria-label="`Delete ${item.name}`"
              @click="emit('delete', item)"
            >
              <Icon name="trash" />
            </button>
          </td>
        </tr>

        <tr v-if="props.items.length === 0">
          <td :colspan="props.manage ? 6 : 5" class="empty">
            No hardware matches this filter.
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}
</style>
