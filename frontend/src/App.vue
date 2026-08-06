<script setup>
// The shell: who is signed in, which view is showing, and the one place that talks to
// the API on the app's behalf.
//
// No router. Four screens with no deep links to honour and no back-button semantics
// worth designing means vue-router would be a dependency carrying state this file
// holds in one ref. Revisit when a URL has to be shareable.
import { computed, onMounted, ref } from 'vue'

import AdminPanel from './components/AdminPanel.vue'
import DashboardView from './components/DashboardView.vue'
import Icon from './components/Icon.vue'
import LoginView from './components/LoginView.vue'
import ReviewQueue from './components/ReviewQueue.vue'
import ToastStack from './components/ToastStack.vue'
import { api, ApiError, handleUnauthorized } from './api.js'

const account = ref(null)
const booting = ref(true)

const view = ref('inventory')
const statusFilter = ref(null)
const sortKey = ref(null)

const items = ref([])
const accounts = ref([])
const busyId = ref(null)
const toasts = ref([])

const isAdmin = computed(() => account.value?.role === 'admin')
const flagged = computed(() => items.value.filter((item) => item.needs_review))

// Counts come from the unfiltered fetch so the chips still read "In Use 1" while the
// table is showing only Repair. A count that changes when you filter by it is useless.
const counts = ref({ total: 0 })

function say(text, tone = 'ok') {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, text, tone })
  setTimeout(() => dismiss(id), tone === 'error' ? 7000 : 4000)
}

function dismiss(id) {
  toasts.value = toasts.value.filter((toast) => toast.id !== id)
}

// Any request can be the one that discovers the session is gone (ADR-0006), so the
// 401 handler lives here rather than in each caller.
handleUnauthorized(() => {
  account.value = null
  items.value = []
  accounts.value = []
})

async function loadInventory() {
  const [visible, everything] = await Promise.all([
    api.hardware({ status: statusFilter.value, sort: sortKey.value }),
    statusFilter.value ? api.hardware({ sort: sortKey.value }) : null,
  ])
  items.value = visible
  const all = everything ?? visible
  counts.value = all.reduce(
    (tally, item) => ({ ...tally, [item.status]: (tally[item.status] ?? 0) + 1 }),
    { total: all.length },
  )
}

async function loadAccounts() {
  if (!isAdmin.value) return
  accounts.value = await api.users()
}

async function refresh() {
  try {
    await Promise.all([loadInventory(), loadAccounts()])
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401) {
      say(e.detail ?? 'Could not load the inventory.', 'error')
    }
  }
}

onMounted(async () => {
  try {
    // The cookie is HttpOnly, so this is the only way to learn whether a reload
    // arrived with a live session, and whose.
    account.value = await api.session()
    await refresh()
  } catch {
    account.value = null
  } finally {
    booting.value = false
  }
})

async function onSignedIn(signedIn) {
  account.value = signedIn
  view.value = 'inventory'
  await refresh()
}

async function act(work, done) {
  try {
    await work()
    await refresh()
    if (done) say(done)
  } catch (e) {
    say(e.detail ?? 'Something went wrong.', 'error')
  } finally {
    busyId.value = null
  }
}

function setFilter(status) {
  statusFilter.value = status
  refresh()
}

function setSort(sort) {
  sortKey.value = sort
  refresh()
}

function toggleRepair(item) {
  const next = item.status === 'Repair' ? 'Available' : 'Repair'
  busyId.value = item.id
  act(
    () => api.setHardwareStatus(item.id, next),
    next === 'Repair' ? `${item.name} marked as Repair` : `${item.name} released from Repair`,
  )
}

function deleteHardware(item) {
  busyId.value = item.id
  act(() => api.deleteHardware(item.id), `${item.name} has been deleted`)
}

function addHardware(item) {
  act(() => api.addHardware(item), `${item.name} added to the inventory`)
}

function addAccount(details) {
  act(() => api.addUser(details), `${details.email} can now sign in`)
}

function setRole(target, role) {
  act(() => api.setRole(target.id, role), `${target.email} is now ${role}`)
}

function deleteAccount(target) {
  act(() => api.deleteUser(target.id), `${target.email} has been removed`)
}

// Clearing the cookie server-side needs a logout route, which does not exist yet
// (BACKLOG.md). Until it does, this drops the client's own state and returns to the
// login screen — honest about being a client-side sign-out, which is why it says so.
function signOut() {
  account.value = null
  items.value = []
  accounts.value = []
  say('Signed out on this device. The session cookie expires with the browser.')
}

const NAV = [
  { id: 'inventory', label: 'Inventory', icon: 'list', admin: false },
  { id: 'review', label: 'Needs review', icon: 'flag', admin: false },
  { id: 'admin', label: 'Admin', icon: 'gear', admin: true },
]

const nav = computed(() => NAV.filter((entry) => !entry.admin || isAdmin.value))
</script>

<template>
  <p v-if="booting" class="empty">Loading…</p>

  <LoginView v-else-if="!account" @signed-in="onSignedIn" />

  <div v-else class="shell">
    <nav class="sidebar" aria-label="Sections">
      <div class="brand">
        <span class="brand-mark"><Icon name="box" :size="18" /></span>
        Hardware<br />Hub
      </div>

      <button
        v-for="entry in nav"
        :key="entry.id"
        type="button"
        class="nav-item"
        :aria-current="view === entry.id ? 'page' : null"
        @click="view = entry.id"
      >
        <Icon :name="entry.icon" />
        {{ entry.label }}
        <span v-if="entry.id === 'review' && flagged.length" class="nav-count">
          {{ flagged.length }}
        </span>
      </button>

      <span class="nav-spacer" />
      <p class="whoami">{{ account.email }} · {{ account.role }}</p>
      <button type="button" class="sign-out" @click="signOut">
        <Icon name="out" /> Sign out
      </button>
    </nav>

    <main class="main">
      <DashboardView
        v-if="view === 'inventory'"
        :items="items"
        :status="statusFilter"
        :sort="sortKey"
        :counts="counts"
        @filter="setFilter"
        @sort="setSort"
      />

      <ReviewQueue v-else-if="view === 'review'" :items="flagged" />

      <AdminPanel
        v-else-if="view === 'admin' && isAdmin"
        :items="items"
        :accounts="accounts"
        :current-email="account.email"
        :busy-id="busyId"
        @add-hardware="addHardware"
        @toggle-repair="toggleRepair"
        @delete-hardware="deleteHardware"
        @add-account="addAccount"
        @set-role="setRole"
        @delete-account="deleteAccount"
      />
    </main>
  </div>

  <ToastStack :toasts="toasts" @dismiss="dismiss" />
</template>
