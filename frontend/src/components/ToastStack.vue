<script setup>
// Confirmations bottom-right, as the wireframes show them. Errors use the same shape:
// a failure is information about the same action, not a different kind of event, and
// the guard's 409 reason (CONTEXT.md) is written to be read by whoever tried.
import Icon from './Icon.vue'

const props = defineProps({ toasts: { type: Array, required: true } })
const emit = defineEmits(['dismiss'])
</script>

<template>
  <div class="toasts" aria-live="polite" aria-atomic="false">
    <div
      v-for="toast in props.toasts"
      :key="toast.id"
      class="toast"
      :class="{ 'is-error': toast.tone === 'error' }"
      :role="toast.tone === 'error' ? 'alert' : 'status'"
    >
      <span class="toast-mark"><Icon :name="toast.tone === 'error' ? 'info' : 'check'" :size="11" /></span>
      <span>{{ toast.text }}</span>
      <button type="button" class="toast-close" aria-label="Dismiss" @click="emit('dismiss', toast.id)">
        ×
      </button>
    </div>
  </div>
</template>
