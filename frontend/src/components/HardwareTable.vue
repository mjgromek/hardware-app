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
function blockedBecause(item) {
  if (item.needs_review) return 'Needs review before it can be rented'
  if (item.status === 'Repair') return 'In Repair'
  if (item.status === 'In Use') return 'Somebody else has it'
  return null
}

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
          <th scope="col"><span class="th-label">Name</span></th>
          <th scope="col"><span class="th-label">Brand</span></th>
          <th scope="col" :aria-sort="props.sort === 'purchase_date' ? 'ascending' : null">
            <button
              type="button"
              class="sort-button"
              @click="emit('sort', props.sort === 'purchase_date' ? null : 'purchase_date')"
            >
              Purchase date
              <span class="sort-arrow">{{ props.sort === 'purchase_date' ? '↑' : '↕' }}</span>
            </button>
          </th>
          <th scope="col"><span class="th-label">Status</span></th>
          <th scope="col"><span class="th-label">Review</span></th>
          <th v-if="props.manage || props.rentable" scope="col">
            <span class="th-label" style="justify-content: flex-end">Actions</span>
          </th>
        </tr>
      </thead>

      <tbody @keydown="onKeydown">
        <tr
          v-for="(item, index) in props.items"
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
          <td class="cell-mono">
            <span v-if="shown(item.purchase_date)">{{ item.purchase_date }}</span>
            <span v-else class="missing" title="No purchase date recorded">—</span>
          </td>
          <td>
            <StatusChip :status="item.status" />
            <span v-if="item.status === 'In Use'" class="held-by">
              {{ heldByMe(item) ? 'you' : item.assigned_to || 'unknown holder' }}
            </span>
          </td>
          <td>
            <span v-if="item.needs_review" class="chip chip-flag" :title="item.review_reason">
              Needs review
            </span>
            <span v-else class="missing">—</span>
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
            <template v-else-if="blockedBecause(item)">
              <span class="blocked-reason">{{ blockedBecause(item) }}</span>
            </template>
            <button
              v-else
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
