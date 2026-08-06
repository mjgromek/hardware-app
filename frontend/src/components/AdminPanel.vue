<script setup>
// Admin: hardware and accounts on one screen, in that order, because hardware is what
// the job is about and accounts are how people get in to do it.
//
// The wireframe's row actions are edit / repair / delete. Edit is not here — there is
// no endpoint that changes a name or brand, and inventing one for a button would be a
// control that fails. See WIREFRAME_JUSTIFICATION.md.
import { ref } from 'vue'

import HardwareTable from './HardwareTable.vue'
import Icon from './Icon.vue'

const props = defineProps({
  items: { type: Array, required: true },
  accounts: { type: Array, required: true },
  currentEmail: { type: String, required: true },
  busyId: { type: [Number, null], default: null },
})

const emit = defineEmits([
  'add-hardware',
  'toggle-repair',
  'delete-hardware',
  'add-account',
  'set-role',
  'delete-account',
])

const addingHardware = ref(false)
const newItem = ref({ name: '', brand: '', purchase_date: '' })

const newAccount = ref({ email: '', password: '', role: 'user' })

function submitHardware() {
  emit('add-hardware', {
    name: newItem.value.name.trim(),
    // Empty inputs are absent fields, not empty strings: the seed stores null for
    // both, and `""` would render as a brand that exists and is blank.
    brand: newItem.value.brand.trim() || null,
    purchase_date: newItem.value.purchase_date || null,
  })
  newItem.value = { name: '', brand: '', purchase_date: '' }
  addingHardware.value = false
}

function submitAccount() {
  emit('add-account', { ...newAccount.value, email: newAccount.value.email.trim() })
  newAccount.value = { email: '', password: '', role: 'user' }
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
      @toggle-repair="emit('toggle-repair', $event)"
      @delete="emit('delete-hardware', $event)"
    />
  </div>

  <div class="panel">
    <div class="panel-head"><h2>Accounts</h2></div>

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
              <button
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

    <form class="panel-head" style="border-top: 1px solid var(--line); border-bottom: 0" @submit.prevent="submitAccount">
      <label class="field" style="flex: 2 1 220px">
        <span>New account email</span>
        <input v-model="newAccount.email" type="email" required placeholder="name@booksy.com" />
      </label>
      <label class="field" style="flex: 1 1 160px">
        <span>Password</span>
        <input v-model="newAccount.password" type="password" required minlength="8" />
      </label>
      <label class="field" style="flex: 0 1 120px">
        <span>Role</span>
        <select v-model="newAccount.role">
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
      </label>
      <button class="button" type="submit" style="align-self: flex-end">Create account</button>
    </form>
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
          <span>Brand <span class="hint">optional</span></span>
          <input v-model="newItem.brand" placeholder="Apple" />
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
