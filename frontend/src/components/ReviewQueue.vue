<script setup>
// The needs-review tab. Not in the wireframes; here because ADR-0003 makes the flag
// a rentability guard — an item nobody can rent and nobody can see is inventory that
// has silently disappeared.
//
// The Review action lives here and only here (ADR-0017 as amended): one place to
// release an item, next to the reason it was held. The main table shows the amber
// marker and offers nothing — a release is a decision, not a row action.
import StatusChip from './StatusChip.vue'

const props = defineProps({
  items: { type: Array, required: true },
  //: Releasing is an admin's decision; a `user` sees the queue and no button.
  isAdmin: { type: Boolean, default: false },
  busyId: { type: [Number, null], default: null },
  //: The row just released: `{ item, fading }` or null. Kept on screen for two
  //: seconds in its resolved state, then faded out — the admin sees the result
  //: rather than watching it vanish (brainstorm §3 Phase 4).
  justResolved: { type: [Object, null], default: null },
})

const emit = defineEmits(['review'])
</script>

<template>
  <h1>Needs review</h1>
  <!-- "Ingestion could not vouch for these records" is how the system describes itself;
       "these items are blocked" is how a person experiences it. Same fact, reader's
       vocabulary, and no ADR number on a screen. -->
  <p class="lede">
    These items are blocked from rental until someone checks them. Releasing one records
    what was fixed.
  </p>

  <div class="panel">
    <div class="panel-head">
      <h2>{{ props.items.length }} flagged {{ props.items.length === 1 ? 'item' : 'items' }}</h2>
    </div>

    <div v-if="props.items.length === 0 && !props.justResolved" class="empty">
      No items awaiting review.
    </div>

    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col"><span class="th-label">Item</span></th>
            <th scope="col"><span class="th-label">Status</span></th>
            <th scope="col"><span class="th-label">Review</span></th>
            <th v-if="props.isAdmin" scope="col">
              <span class="th-label" style="justify-content: flex-end">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-if="props.justResolved"
            class="is-resolved"
            :class="{ 'is-fading': props.justResolved.fading }"
          >
            <td class="cell-name">{{ props.justResolved.item.name }}</td>
            <td><StatusChip :status="props.justResolved.item.status" /></td>
            <td class="resolved-note">Resolved — released for rental.</td>
            <td v-if="props.isAdmin" class="cell-actions"></td>
          </tr>
          <tr v-for="item in props.items" :key="item.id" class="is-flagged">
            <td class="cell-name">
              {{ item.name }}
              <span v-if="item.brand" class="hint">{{ item.brand }}</span>
              <span v-else class="missing" title="No brand recorded">— no brand</span>
            </td>
            <td><StatusChip :status="item.status" :needs-review="item.needs_review" /></td>
            <td>{{ item.review_reason ?? 'No reason recorded.' }}</td>
            <td v-if="props.isAdmin" class="cell-actions">
              <button
                type="button"
                class="button button-quiet"
                :disabled="props.busyId === item.id"
                @click="emit('review', item)"
              >
                Review
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
