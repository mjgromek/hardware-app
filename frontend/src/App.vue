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
import MyRentals from './components/MyRentals.vue'
import ReasonDialog from './components/ReasonDialog.vue'
import ReviewQueue from './components/ReviewQueue.vue'
import ToastStack from './components/ToastStack.vue'
import { api, ApiError, handleUnauthorized } from './api.js'
import { sound } from './sound.js'

// Theme. **Light is the default and `prefers-color-scheme` is deliberately not read.**
// Every visitor lands on the light theme — it is what the wireframe shows and what a
// reviewer should see first — and dark is opt-in. Once chosen it sticks, because the
// choice is stored rather than re-derived from the OS on each visit.
const THEME_KEY = 'hardware-hub-theme'
const theme = ref(localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light')

function applyTheme(next) {
  // The attribute is what the token layer keys on; light removes it entirely so the
  // `:root` defaults apply unmodified rather than being overridden back to themselves.
  if (next === 'dark') document.documentElement.setAttribute('data-theme', 'dark')
  else document.documentElement.removeAttribute('data-theme')
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem(THEME_KEY, theme.value)
  applyTheme(theme.value)
}

applyTheme(theme.value)

// Sound is off until asked for, and the toggle sits beside the theme one. The four
// events are in ADR-0018; each is paired with a toast at its call site, so muting
// removes a channel rather than the information.
const soundOn = ref(sound.enabled)

function toggleSound() {
  soundOn.value = !soundOn.value
  sound.enabled = soundOn.value
  if (soundOn.value) sound.rent()   // one tone, so "on" is audible immediately
}

const account = ref(null)
const booting = ref(true)

const view = ref('inventory')
const statusFilter = ref(null)
const sortKey = ref(null)

const items = ref([])
const mine = ref([])
const accounts = ref([])

//: The pending admin override, or null. One dialog serves all three verbs (ADR-0010).
const override = ref(null)
const busyId = ref(null)
const toasts = ref([])

//: `{ mode, items }` from the last search, or null when the dashboard shows the
//: whole inventory. The mode is displayed, not swallowed (ADR-0016).
const searchResults = ref(null)
const searching = ref(false)

//: The auditor's last run: findings, or the refusal it answered with. Computed
//: server-side per run and never persisted (ADR-0014), so this is the only copy.
const findings = ref(null)
const auditError = ref(null)
const auditing = ref(false)

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
  mine.value = []
  accounts.value = []
})

async function loadInventory() {
  const [visible, everything] = await Promise.all([
    api.hardware({ status: statusFilter.value, sort: sortKey.value }),
    statusFilter.value ? api.hardware({ sort: sortKey.value }) : null,
  ])
  // Two of ADR-0018's four events are about somebody *else's* action — a user rents an
  // item, an item enters review — and there is no realtime channel to learn them from.
  // So they are derived by diffing this fetch against the previous one: an admin hears
  // them the next time their client refetches, which is after every action they take.
  // Notification on refresh, not realtime, and ADR-0018 says so rather than implying it.
  const previous = items.value
  items.value = visible
  if (isAdmin.value && previous.length) announceChanges(previous, visible)
  const all = everything ?? visible
  counts.value = all.reduce(
    (tally, item) => ({ ...tally, [item.status]: (tally[item.status] ?? 0) + 1 }),
    { total: all.length },
  )
}

async function loadMine() {
  mine.value = await api.hardware({ heldBy: 'me' })
}

function announceChanges(before, after) {
  const was = new Map(before.map((item) => [item.id, item]))
  for (const item of after) {
    const prior = was.get(item.id)
    if (!prior) continue
    // Somebody took something out. Not fired for the admin's own rent — that path
    // already reported itself as a confirmed action.
    if (prior.status !== 'In Use' && item.status === 'In Use' && item.assigned_to !== account.value?.email) {
      sound.rent()
      say(`${item.name} was taken by ${item.assigned_to ?? 'somebody'}`)
    }
    if (!prior.needs_review && item.needs_review) {
      sound.flag()
      say(`${item.name} entered review`)
    }
    // A cleared flag is not always a release. Since the second Phase 4 amendment a
    // review can conclude in Repair, which clears the flag too — and announcing "was
    // released from review" over an item an admin just declared unfit is the false
    // record ADR-0017 keeps closing, this time in the copy rather than the database.
    // The Repair branch below reports that conclusion in its own words.
    if (prior.needs_review && !item.needs_review && item.status !== 'Repair') {
      sound.resolve()
      say(`${item.name} was released from review`)
    }
    if (prior.status !== 'Repair' && item.status === 'Repair') {
      sound.repair()
      say(`${item.name} was sent to Repair`)
    }
  }
}

async function loadAccounts() {
  if (!isAdmin.value) return
  accounts.value = await api.users()
}

async function refresh() {
  try {
    await Promise.all([loadInventory(), loadMine(), loadAccounts()])
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

async function act(work, done, voice) {
  try {
    await work()
    await refresh()
    if (done) {
      voice?.()
      say(done)
    }
  } catch (e) {
    // A 409 is a guard refusing with a readable reason (CONTEXT.md) — a different
    // event from a network failure, and the only error worth its own voice.
    if (e instanceof ApiError && e.status === 409) sound.refused()
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
    next === 'Repair' ? sound.repair : sound.resolve,
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

// A refused rental arrives as a 409 whose detail is written to be read (CONTEXT.md):
// "in Repair", "somebody else has it", "needs review before it can be rented" are
// different facts, and `act` already surfaces `detail` verbatim rather than a generic
// failure. Nothing here flattens them.
function rentItem(item) {
  busyId.value = item.id
  act(() => api.rent(item.id), `${item.name} is yours`, sound.rent)
}

function returnItem(item) {
  busyId.value = item.id
  act(() => api.returnItem(item.id), `${item.name} returned`, sound.returned)
}

function askForceReturn(item) {
  override.value = {
    kind: 'force-return',
    item,
    title: 'Recall this item',
    subject: `${item.name}, held by ${item.assigned_to || 'an unknown holder'}`,
    prompt: 'Why is it being recalled?',
    confirm: 'Recall it',
  }
}

function askClearReview(item) {
  override.value = {
    kind: 'clear-review',
    item,
    //: The form is prefilled from the item, so the release can correct the record it
    //: certifies (ADR-0017 as amended).
    editable: true,
    title: 'Review this item',
    subject: `${item.name} — ${item.review_reason || 'flagged at import'}`,
    prompt: 'What was fixed? The note must start with "fixed:".',
    confirm: 'Record the outcome',
    //: A review concludes two ways (ADR-0017, second Phase 4 amendment). The dialog is
    //: the only place that choice exists, so this is the only verb that sets it.
    outcomes: true,
    // The server refuses anything that does not state a change (ADR-0017 as
    // amended); prefilling the prefix turns the rule into a prompt.
    prefill: 'fixed: ',
  }
}

//: The row just released, kept visible in its resolved state for two seconds and
//: then faded — the admin sees the result rather than watching it vanish.
const justResolved = ref(null)

function markResolved(item) {
  justResolved.value = { item, fading: false }
  setTimeout(() => {
    if (justResolved.value?.item.id === item.id) justResolved.value.fading = true
  }, 2000)
  setTimeout(() => {
    if (justResolved.value?.item.id === item.id) justResolved.value = null
  }, 2600)
}

// From a finding, not from a row: the auditor proposed (ADR-0014), and this is the
// human deciding (ADR-0017). The reason arrives prefilled from the finding and stays
// editable — what gets recorded is whatever the admin leaves in the field.
function askFlagReview(finding) {
  const item = items.value.find((candidate) => candidate.id === finding.item_id)
  override.value = {
    kind: 'flag-review',
    item: item ?? { id: finding.item_id, name: `item ${finding.item_id}` },
    title: 'Flag for review',
    subject: `${item?.name ?? `item ${finding.item_id}`} — ${finding.kind.replaceAll('_', ' ')}`,
    prompt: 'Why is it being restricted?',
    confirm: 'Flag it',
    prefill: `${finding.explanation} Evidence: ${finding.evidence}`,
  }
}

function askEditHardware(item) {
  override.value = {
    kind: 'edit',
    item,
    editable: true,
    requireReason: false,
    title: 'Edit item',
    subject: item.name,
    prompt: '',
    confirm: 'Save changes',
  }
}

function submitOverride(reason, edits = {}, outcome = 'released') {
  const { kind, item } = override.value
  override.value = null
  busyId.value = item.id
  if (kind === 'edit') {
    if (!Object.keys(edits).length) {
      busyId.value = null
      return say('Nothing changed.')
    }
    act(() => api.editHardware(item.id, edits), `${item.name} updated`, sound.returned)
  } else if (kind === 'force-return') {
    act(() => api.forceReturn(item.id, reason), `${item.name} recalled`)
  } else if (kind === 'flag-review') {
    act(() => api.flagReview(item.id, reason), `${item.name} is flagged and unrentable`)
  } else {
    // Two outcomes, two messages and two sounds. Telling an admin who just declared a
    // battery unsafe that the item was "released" would be the false record again, one
    // layer up — the toast is what they read to confirm what they did.
    const repairing = outcome === 'repair'
    act(
      async () => {
        await api.clearReview(item.id, reason, edits, outcome)
        markResolved(item)
      },
      repairing
        ? `${item.name} sent to Repair — stays unrentable`
        : `${item.name} released — resolved`,
      // No voice here: the change observer plays `repair` when it sees the status move,
      // exactly as it plays `resolve` for a release. Passing one too would double it.
    )
  }
}

async function runSearch(query) {
  searching.value = true
  try {
    searchResults.value = await api.search(query)
  } catch (e) {
    say(e.detail ?? 'Search failed.', 'error')
  } finally {
    searching.value = false
  }
}

function clearSearch() {
  searchResults.value = null
}

async function runAudit() {
  auditing.value = true
  auditError.value = null
  try {
    findings.value = (await api.runAudit()).findings
  } catch (e) {
    // The refusal is a result, not a crash: ADR-0016 wrote the 503's detail to be
    // shown to exactly this admin, so it lands in the panel rather than a toast.
    findings.value = null
    auditError.value = e.detail ?? 'The audit could not run.'
  } finally {
    auditing.value = false
  }
}

// Clearing the cookie server-side needs a logout route, which does not exist yet
// (BACKLOG.md). Until it does, this drops the client's own state and returns to the
// login screen — honest about being a client-side sign-out, which is why it says so.
function signOut() {
  account.value = null
  items.value = []
  mine.value = []
  accounts.value = []
  say('Signed out on this device. The session cookie expires with the browser.')
}

const NAV = [
  { id: 'inventory', label: 'Inventory', icon: 'list', admin: false },
  { id: 'mine', label: 'My rentals', icon: 'clock', admin: false },
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
        <span v-if="entry.id === 'mine' && mine.length" class="nav-count">
          {{ mine.length }}
        </span>
      </button>

      <span class="nav-spacer" />
      <button
        type="button"
        class="theme-toggle"
        :aria-pressed="soundOn"
        @click="toggleSound"
      >
        <Icon :name="soundOn ? 'bell' : 'bell-off'" />
        {{ soundOn ? 'Sounds on' : 'Sounds off' }}
      </button>
      <button
        type="button"
        class="theme-toggle"
        :aria-pressed="theme === 'dark'"
        @click="toggleTheme"
      >
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" />
        {{ theme === 'dark' ? 'Light theme' : 'Dark theme' }}
      </button>
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
        :current-email="account.email"
        :busy-id="busyId"
        :search-results="searchResults"
        :searching="searching"
        @filter="setFilter"
        @sort="setSort"
        @rent="rentItem"
        @return="returnItem"
        @search="runSearch"
        @clear-search="clearSearch"
      />

      <MyRentals
        v-else-if="view === 'mine'"
        :items="mine"
        :current-email="account.email"
        :busy-id="busyId"
        @return="returnItem"
      />

      <ReviewQueue
        v-else-if="view === 'review'"
        :items="flagged"
        :is-admin="isAdmin"
        :busy-id="busyId"
        :just-resolved="justResolved"
        @review="askClearReview"
      />

      <AdminPanel
        v-else-if="view === 'admin' && isAdmin"
        :items="items"
        :accounts="accounts"
        :current-email="account.email"
        :busy-id="busyId"
        :findings="findings"
        :audit-error="auditError"
        :auditing="auditing"
        @add-hardware="addHardware"
        @toggle-repair="toggleRepair"
        @delete-hardware="deleteHardware"
        @force-return="askForceReturn"
        @clear-review="askClearReview"
        @edit-hardware="askEditHardware"
        @flag-finding="askFlagReview"
        @run-audit="runAudit"
        @add-account="addAccount"
        @set-role="setRole"
        @delete-account="deleteAccount"
      />
    </main>
  </div>

  <ReasonDialog
    :open="override !== null"
    :item="override?.editable ? override.item : null"
    :require-reason="override?.requireReason !== false"
    :title="override?.title ?? ''"
    :subject="override?.subject ?? ''"
    :prompt="override?.prompt ?? ''"
    :confirm="override?.confirm ?? ''"
    :prefill="override?.prefill ?? ''"
    :outcomes="override?.outcomes === true"
    @submit="submitOverride"
    @cancel="override = null"
  />

  <ToastStack :toasts="toasts" @dismiss="dismiss" />
</template>
