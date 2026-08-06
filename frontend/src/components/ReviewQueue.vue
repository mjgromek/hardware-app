<script setup>
// The needs_review queue. Not in the wireframes at all, and here because ADR-0003
// makes the flag a rentability guard: an item nobody can rent and nobody can see is
// inventory that has silently disappeared.
//
// Read-only, and that is a gap rather than a decision. Nothing in the API clears the
// flag — ADR-0003 records it as an unresolved consequence and BACKLOG.md keeps it open
// — so this screen names the state and says plainly what it cannot do, instead of
// offering a button that would 404.
import StatusChip from './StatusChip.vue'

const props = defineProps({ items: { type: Array, required: true } })
</script>

<template>
  <h1>Needs review</h1>
  <p class="lede">
    Ingestion could not vouch for these records, so they are blocked from rental until
    someone checks the equipment (ADR-0003). The reason is the one ingestion recorded
    at import.
  </p>

  <div class="panel">
    <div class="panel-head">
      <h2>{{ props.items.length }} flagged {{ props.items.length === 1 ? 'item' : 'items' }}</h2>
    </div>

    <div v-if="props.items.length === 0" class="empty">
      Nothing is flagged. Every item in the inventory is accounted for.
    </div>

    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col"><span class="th-label">Item</span></th>
            <th scope="col"><span class="th-label">Status</span></th>
            <th scope="col"><span class="th-label">Why it was flagged</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in props.items" :key="item.id" class="is-flagged">
            <td class="cell-name">
              {{ item.name }}
              <span v-if="item.brand" class="hint">{{ item.brand }}</span>
              <span v-else class="missing" title="No brand recorded">— no brand</span>
            </td>
            <td><StatusChip :status="item.status" /></td>
            <td>{{ item.review_reason ?? 'No reason recorded.' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <p class="lede" style="margin-top: 16px">
    Clearing a flag needs a decision that has not been made yet — what evidence
    releases an item, and who records it. Until then a flagged item is released by
    editing the database directly. Tracked in <code>BACKLOG.md</code>.
  </p>
</template>
