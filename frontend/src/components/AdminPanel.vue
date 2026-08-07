<script setup>
// Admin: hardware and accounts on one screen, in that order, because hardware is what
// the job is about and accounts are how people get in to do it.
//
// The wireframe's row actions are edit / repair / delete, and all three are here as of
// Phase 4: `PATCH /api/hardware/{id}` covers name, brand, purchase date, serial,
// category and notes. The Phase 1 comment explaining why edit was absent stood after
// the endpoint shipped and is deleted rather than edited — it had been false since
// 0e0be61.
//
import { nextTick, ref, watch } from 'vue'

import HardwareTable from './HardwareTable.vue'
import Icon from './Icon.vue'

const props = defineProps({
  items: { type: Array, required: true },
  accounts: { type: Array, required: true },
  currentEmail: { type: String, required: true },
  busyId: { type: [Number, null], default: null },
  // The auditor's last run (ADR-0014): findings, or the refusal ADR-0016 wrote to be
  // shown to exactly this admin. Null until a run is asked for — nothing is cached.
  findings: { type: [Array, null], default: null },
  auditError: { type: [String, null], default: null },
  auditing: { type: Boolean, default: false },
})

const emit = defineEmits([
  'add-hardware',
  'toggle-repair',
  'delete-hardware',
  'force-return',
  'edit-hardware',
  'flag-finding',
  'run-audit',
  'add-account',
  'set-role',
  'delete-account',
])

const KIND_LABELS = {
  status_contradiction: 'Status contradiction',
  unidentifiable: 'Unidentifiable',
  probable_misspelling: 'Probable misspelling',
}

function itemFor(finding) {
  return props.items.find((item) => item.id === finding.item_id) ?? null
}

const addingHardware = ref(false)
const newItem = ref({ name: '', brand: '', purchase_date: '', serial_number: '', category: '' })

//: The closed set the server enforces (422 outside it). Listed here only so the
//: dropdown can render it — the server is the guard, this is the affordance.
const CATEGORIES = ['Laptop', 'Mobile', 'Tablet', 'Monitor', 'Accessory']

//: Accounts belong to Booksy employees, and the server refuses anything else at creation
//: (ADR-0019). Prefilled rather than merely hinted, so the rule is visible before the
//: admin types instead of arriving as a 422 after they have filled the whole form.
const COMPANY_DOMAIN = '@booksy.com'

const addingAccount = ref(false)
const newAccount = ref({ email: COMPANY_DOMAIN, password: '', role: 'user' })
const emailInput = ref(null)

/** Put the caret before the domain, so typing continues the address rather than the domain.
 *
 * `autofocus` alone leaves the caret at the end, where the first keystroke would produce
 * `@booksy.comj.doe`. Selecting nothing at offset 0 keeps the field an ordinary email
 * input: a pasted full address still overwrites cleanly, and the domain stays editable
 * for anyone who needs to correct it.
 */
function focusBeforeDomain() {
  const field = emailInput.value
  if (!field) return
  field.focus()
  field.setSelectionRange(0, 0)
}

// `v-if` means the input does not exist until the modal renders, so the caret has to be
// placed on the tick after it opens — not in `focusBeforeDomain`'s caller.
watch(addingAccount, async (open) => {
  if (!open) return
  await nextTick()
  focusBeforeDomain()
})

function submitHardware() {
  emit('add-hardware', {
    name: newItem.value.name.trim(),
    // Empty inputs are absent fields, not empty strings: the seed stores null for
    // both, and `""` would render as a brand that exists and is blank.
    brand: newItem.value.brand.trim() || null,
    purchase_date: newItem.value.purchase_date || null,
    serial_number: newItem.value.serial_number.trim() || null,
    category: newItem.value.category || null,
  })
  newItem.value = { name: '', brand: '', purchase_date: '', serial_number: '', category: '' }
  addingHardware.value = false
}

function submitAccount() {
  emit('add-account', { ...newAccount.value, email: newAccount.value.email.trim() })
  newAccount.value = { email: COMPANY_DOMAIN, password: '', role: 'user' }
  addingAccount.value = false
}
</script>

<template>
  <div class="main-head">
    <h1>Admin</h1>
    <button type="button" class="button" @click="addingHardware = true">
      <Icon name="plus" /> Add hardware
    </button>
  </div>
  <p class="lede">
    Add and retire equipment, move items in and out of Repair, and manage who can sign
    in.
  </p>

  <div class="panel">
    <div class="panel-head"><h2>Hardware</h2></div>
    <HardwareTable
      :items="props.items"
      manage
      :busy-id="props.busyId"
      :current-email="props.currentEmail"
      @toggle-repair="emit('toggle-repair', $event)"
      @delete="emit('delete-hardware', $event)"
      @force-return="emit('force-return', $event)"
      @edit-hardware="emit('edit-hardware', $event)"
    />
  </div>

  <!-- Flat, in the search bar's language: same fill, same radius, no card border. It is
       a second reading of the same inventory, so it should recede rather than compete
       with the table it comments on. -->
  <div class="panel is-flat">
    <div class="panel-head">
      <h2>Inventory Auditor</h2>
      <button type="button" class="button" :disabled="props.auditing" @click="emit('run-audit')">
        {{ props.auditing ? 'Auditing…' : 'Run audit' }}
      </button>
    </div>

    <!-- The refusal is a result (ADR-0016): no key or no provider means a readable
         reason here, never a quieter answer pretending to be the audit. -->
    <p v-if="props.auditError" class="empty">{{ props.auditError }}</p>
    <!-- Product copy: one sentence, no internal vocabulary, no ADR numbers. The
         propose-never-dispose boundary is still communicated — "flagging is yours" says
         it in the reader's terms — but the reasoning for it lives in docs/adr/, not on
         a screen somebody is trying to use. -->
    <p v-else-if="props.findings === null" class="empty">
      Reviews the catalogue and suggests items worth checking.
    </p>
    <p v-else-if="!props.findings.length" class="empty">
      The model reported nothing it is allowed to say. A clean catalogue and a model
      having a bad day look the same here — run it again before believing it.
    </p>
    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col"><span class="th-label">Item</span></th>
            <th scope="col"><span class="th-label">Finding</span></th>
            <th scope="col"><span class="th-label">Evidence</span></th>
            <th scope="col"><span class="th-label" style="justify-content: flex-end">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="finding in props.findings" :key="`${finding.item_id}-${finding.kind}`">
            <td class="cell-name">{{ itemFor(finding)?.name ?? `item ${finding.item_id}` }}</td>
            <td>
              <span class="chip">{{ KIND_LABELS[finding.kind] ?? finding.kind }}</span>
              <div class="hint">{{ finding.explanation }}</div>
            </td>
            <td class="cell-name"><em>{{ finding.evidence }}</em></td>
            <td class="cell-actions">
              <span v-if="itemFor(finding)?.needs_review" class="hint">already flagged</span>
              <button
                v-else
                type="button"
                class="button button-quiet"
                @click="emit('flag-finding', finding)"
              >
                Flag for review
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="panel">
    <div class="panel-head">
      <h2>Accounts</h2>
      <button type="button" class="button" @click="addingAccount = true">
        <Icon name="plus" /> Add account
      </button>
    </div>

    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col"><span class="th-label">Email</span></th>
            <th scope="col"><span class="th-label">Role</span></th>
            <th scope="col"><span class="th-label" style="justify-content: flex-end">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="account in props.accounts" :key="account.id">
            <td class="cell-name">
              {{ account.email }}
              <span v-if="account.email === props.currentEmail" class="hint">(you)</span>
            </td>
            <td><span class="chip chip-role">{{ account.role }}</span></td>
            <td class="cell-actions">
              <button
                type="button"
                class="button button-quiet"
                @click="emit('set-role', account, account.role === 'admin' ? 'user' : 'admin')"
              >
                {{ account.role === 'admin' ? 'Make user' : 'Make admin' }}
              </button>
              <!-- Not on your own row. For the sole admin it can only die on the
                   zero-admin guard (ADR-0005) — a control that cannot succeed, the
                   409 toast dressed up as an action. With other admins present it
                   would "succeed" by deleting the account whose session you are
                   inside; an account's end belongs to a colleague either way. -->
              <button
                v-if="account.email !== props.currentEmail"
                type="button"
                class="button button-danger"
                @click="emit('delete-account', account)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

  </div>

  <!-- The form moves into a modal. Inline, it sat permanently open under the account
       list — three empty fields and a submit button on a screen whose job is reading who
       has access, so the rare action occupied the same weight as the common one. -->
  <div v-if="addingAccount" class="scrim" @click.self="addingAccount = false">
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="add-account-title">
      <div class="dialog-head">
        <div>
          <h2 id="add-account-title">Add account</h2>
          <p>They can sign in as soon as you save.</p>
        </div>
      </div>

      <form @submit.prevent="submitAccount">
        <label class="field">
          <span>Email</span>
          <!-- `type="text"`, not `type="email"`, for one concrete reason: `setSelectionRange`
               throws `InvalidStateError` on an email input, so the caret cannot be placed
               before the prefilled domain. `inputmode="email"` keeps the phone keyboard,
               and `pattern` keeps the browser's own refusal — now for the *company*
               domain rather than for any address at all, which is the stricter rule. -->
          <input
            ref="emailInput"
            v-model="newAccount.email"
            type="text"
            inputmode="email"
            required
            pattern="[^@\s]+@[Bb][Oo][Oo][Kk][Ss][Yy]\.[Cc][Oo][Mm]"
            title="Accounts must be on the @booksy.com domain"
            placeholder="name@booksy.com"
          />
        </label>
        <label class="field">
          <span>Password</span>
          <input v-model="newAccount.password" type="password" required minlength="8" />
        </label>

        <!-- Two toggles rather than a select. There are exactly two roles and the choice
             decides what this person can do to the inventory — a dropdown hides one of
             two options behind a click and makes the more dangerous one no harder to
             pick than the safer one. Side by side, the choice is visible and deliberate. -->
        <div class="field">
          <span class="field-label">Role</span>
          <div class="toggle-group" role="group" aria-label="Role">
            <button
              type="button"
              class="toggle"
              :aria-pressed="newAccount.role === 'user'"
              @click="newAccount.role = 'user'"
            >
              User
            </button>
            <button
              type="button"
              class="toggle"
              :aria-pressed="newAccount.role === 'admin'"
              @click="newAccount.role = 'admin'"
            >
              Admin
            </button>
          </div>
        </div>

        <div class="dialog-actions">
          <button type="button" class="button button-quiet" @click="addingAccount = false">
            Cancel
          </button>
          <button class="button" type="submit">Add account</button>
        </div>
      </form>
    </div>
  </div>

  <div v-if="addingHardware" class="scrim" @click.self="addingHardware = false">
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="add-hardware-title">
      <div class="dialog-head">
        <div>
          <h2 id="add-hardware-title">Add hardware</h2>
          <p>New items join the inventory as Available.</p>
        </div>
      </div>

      <form @submit.prevent="submitHardware">
        <label class="field">
          <span>Name</span>
          <input v-model="newItem.name" required autofocus placeholder="MacBook Pro 16&quot;" />
        </label>
        <label class="field">
          <span>Serial number <span class="hint">optional</span></span>
          <input v-model="newItem.serial_number" placeholder="MBP-2024-001" />
        </label>
        <label class="field">
          <span>Brand <span class="hint">optional</span></span>
          <input v-model="newItem.brand" placeholder="Apple" />
        </label>
        <label class="field">
          <span>Category <span class="hint">optional</span></span>
          <select v-model="newItem.category">
            <option value="">Select a category</option>
            <option v-for="value in CATEGORIES" :key="value" :value="value">{{ value }}</option>
          </select>
        </label>
        <label class="field">
          <span>Purchase date <span class="hint">optional</span></span>
          <input v-model="newItem.purchase_date" type="date" />
        </label>

        <div class="dialog-actions">
          <button type="button" class="button button-quiet" @click="addingHardware = false">
            Cancel
          </button>
          <button class="button" type="submit">Add hardware</button>
        </div>
      </form>
    </div>
  </div>
</template>
