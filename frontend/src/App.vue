<script setup>
import { onMounted, ref } from 'vue'

const items = ref([])
const error = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    // Same origin (ADR-0001) — no host, no CORS, no configuration to get wrong.
    const response = await fetch('/api/hardware')
    if (!response.ok) throw new Error(`API returned ${response.status}`)
    items.value = await response.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main>
    <h1>Hardware Hub</h1>

    <p v-if="loading">Loading inventory…</p>
    <p v-else-if="error" class="error">Could not load inventory: {{ error }}</p>
    <p v-else-if="items.length === 0">No hardware items yet. Has the seed been run?</p>

    <table v-else>
      <caption>{{ items.length }} items</caption>
      <thead>
        <tr>
          <th>Name</th>
          <th>Brand</th>
          <th>Purchase date</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.id">
          <td>{{ item.name || '—' }}</td>
          <td>{{ item.brand || '—' }}</td>
          <td>{{ item.purchase_date || '—' }}</td>
          <td>
            {{ item.status }}
            <!-- needs_review is a rentability guard, not a badge (ADR-0003), so
                 it is shown wherever status is shown. -->
            <span v-if="item.needs_review" class="flag" :title="item.review_reason">
              needs review
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </main>
</template>

<style>
/* Legibility only. Phase 1 does the design pass. */
body {
  font-family: system-ui, sans-serif;
  line-height: 1.5;
  margin: 2rem;
  color: #1a1a1a;
}
h1 {
  font-size: 1.5rem;
}
table {
  border-collapse: collapse;
  width: 100%;
  max-width: 60rem;
}
caption {
  text-align: left;
  padding-bottom: 0.5rem;
  color: #666;
}
th,
td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #ddd;
}
th {
  font-weight: 600;
}
.flag {
  font-size: 0.8rem;
  padding: 0.1rem 0.4rem;
  border: 1px solid #b45309;
  border-radius: 0.2rem;
  color: #b45309;
  white-space: nowrap;
}
.error {
  color: #b91c1c;
}
</style>
