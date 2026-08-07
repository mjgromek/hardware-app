<script setup>
// One dialog for both admin overrides, because ADR-0010 makes them one kind of event:
// an admin doing something an ordinary user could not, with a reason attached. The
// reason is mandatory server-side, so it is `required` here — a client that lets you
// submit an empty one just turns a considered refusal into a 422.
import { nextTick, ref, watch } from 'vue'

//: The six editable fields, in the order the form shows them. `notes` is last and
//: multi-line because it is prose rather than a value — and it is the field a release
//: most often has to correct, since the note is frequently the fault itself
//: ("Battery swelling, do not issue without service").
const EDITABLE = [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'brand', label: 'Brand', type: 'text' },
  { key: 'purchase_date', label: 'Purchase date', type: 'date' },
  { key: 'serial_number', label: 'Serial number', type: 'text' },
  { key: 'category', label: 'Category', type: 'select' },
  { key: 'notes', label: 'Notes', type: 'textarea' },
]

const CATEGORIES = ['Laptop', 'Mobile', 'Tablet', 'Monitor', 'Accessory']

const props = defineProps({
  open: { type: Boolean, default: false },
  //: The item being edited, or `null` for the reason-only verbs (force-return,
  //: flag-review). When present the form renders the six fields prefilled, because an
  //: action that certifies a change must be able to make it — a release note saying
  //: "fixed: corrected the date" beside a field the admin could not reach is the false
  //: record ADR-0017 was amended to close.
  item: { type: Object, default: null },
  //: Admin edit is an edit with no certification: same fields, no note.
  requireReason: { type: Boolean, default: true },
  title: { type: String, required: true },
  // What the reason is *for*, in the user's words. "Recalling the Sony WH-1000XM4 from
  // j.doe@booksy.com" tells them what they are about to do; "Confirm action" does not.
  subject: { type: String, default: '' },
  prompt: { type: String, required: true },
  confirm: { type: String, required: true },
  busy: { type: Boolean, default: false },
  // Pre-written words the admin may edit before submitting — the flag-from-finding
  // flow (ADR-0017): the auditor's explanation is a starting point, and what gets
  // recorded is whatever the human leaves in the field, because the claim is theirs.
  prefill: { type: String, default: '' },
})

const emit = defineEmits(['submit', 'cancel'])
const reason = ref('')
const field = ref(null)
const draft = ref({})

function resetDraft() {
  draft.value = {}
  for (const { key } of EDITABLE) draft.value[key] = props.item?.[key] ?? ''
}

//: Only what actually changed. `''` maps back to `null` so clearing a field is
//: expressible, but an untouched empty field is not sent at all — the difference
//: between "make this empty" and "I did not look at this".
function changedFields() {
  if (!props.item) return {}
  const out = {}
  for (const { key } of EDITABLE) {
    const before = props.item[key] ?? ''
    const now = draft.value[key] ?? ''
    if (String(now) !== String(before)) out[key] = now === '' ? null : now
  }
  return out
}

// `autofocus` is honoured on page load, not when an element is inserted later — the
// dialog opened with focus still on the button that opened it, so typing went nowhere.
// Focusing explicitly is also what makes Escape-then-retype work for a keyboard user.
// Watched as a pair, because the dialog is reused across verbs: `open` going true is
// the trigger, and `item` is what the form has to be filled from. `resetDraft` runs on
// every open so a second review never shows the previous item's values.
watch(
  () => [props.open, props.item],
  async ([open]) => {
    if (!open) return
    reason.value = props.prefill
    resetDraft()
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

      <form @submit.prevent="emit('submit', reason.trim(), changedFields())">
        <template v-if="props.item">
          <label v-for="f in EDITABLE" :key="f.key" class="field">
            <span>{{ f.label }}</span>
            <textarea v-if="f.type === 'textarea'" v-model="draft[f.key]" rows="3" />
            <select v-else-if="f.type === 'select'" v-model="draft[f.key]">
              <option value="">—</option>
              <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
            </select>
            <input v-else v-model="draft[f.key]" :type="f.type" />
          </label>
        </template>
        <label v-if="props.requireReason" class="field">
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
          <button
            class="button"
            type="submit"
            :disabled="props.busy || (props.requireReason && !reason.trim())"
          >
            {{ props.confirm }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
