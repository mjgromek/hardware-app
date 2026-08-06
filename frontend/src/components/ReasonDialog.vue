<script setup>
// One dialog for both admin overrides, because ADR-0010 makes them one kind of event:
// an admin doing something an ordinary user could not, with a reason attached. The
// reason is mandatory server-side, so it is `required` here — a client that lets you
// submit an empty one just turns a considered refusal into a 422.
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  // What the reason is *for*, in the user's words. "Recalling the Sony WH-1000XM4 from
  // j.doe@booksy.com" tells them what they are about to do; "Confirm action" does not.
  subject: { type: String, default: '' },
  prompt: { type: String, required: true },
  confirm: { type: String, required: true },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['submit', 'cancel'])
const reason = ref('')
const field = ref(null)

// `autofocus` is honoured on page load, not when an element is inserted later — the
// dialog opened with focus still on the button that opened it, so typing went nowhere.
// Focusing explicitly is also what makes Escape-then-retype work for a keyboard user.
watch(
  () => props.open,
  async (open) => {
    if (!open) return
    reason.value = ''
    await nextTick()
    field.value?.focus()
  },
)

function onKeydown(event) {
  if (event.key === 'Escape') emit('cancel')
}
</script>

<template>
  <div v-if="props.open" class="scrim" @click.self="emit('cancel')" @keydown="onKeydown">
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="reason-title">
      <div class="dialog-head">
        <div>
          <h2 id="reason-title">{{ props.title }}</h2>
          <p v-if="props.subject">{{ props.subject }}</p>
        </div>
      </div>

      <form @submit.prevent="emit('submit', reason.trim())">
        <label class="field">
          <span>{{ props.prompt }}</span>
          <input
            ref="field"
            v-model="reason"
            required
            placeholder="Bench-tested by IT; battery replaced"
          />
          <span class="hint">
            Recorded against your name in the audit trail. It is what a later question
            about this item gets answered with.
          </span>
        </label>

        <div class="dialog-actions">
          <button type="button" class="button button-quiet" @click="emit('cancel')">
            Cancel
          </button>
          <button class="button" type="submit" :disabled="props.busy || !reason.trim()">
            {{ props.confirm }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
