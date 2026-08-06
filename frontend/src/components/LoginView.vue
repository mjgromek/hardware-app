<script setup>
// The one screen an unauthenticated caller can reach. `GET /` stays public precisely
// so this is reachable (ADR-0006); everything behind it needs the session cookie.
import { ref } from 'vue'
import Icon from './Icon.vue'
import { api, ApiError } from '../api.js'

const emit = defineEmits(['signed-in'])

const email = ref('')
const password = ref('')
const error = ref(null)
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = null
  try {
    const account = await api.logIn(email.value, password.value)
    emit('signed-in', account)
  } catch (e) {
    // The server answers every bad credential identically, and so does this: naming
    // which half was wrong would undo the work the API does not to enumerate accounts.
    error.value = e instanceof ApiError ? e.detail : 'Could not reach the server.'
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login-card">
      <span class="brand-mark"><Icon name="box" :size="18" /></span>

      <div class="login-title">
        <h1>Hardware Hub</h1>
        <p>Sign in to manage company equipment</p>
      </div>

      <form @submit.prevent="submit">
        <label class="field">
          <span>Email</span>
          <input
            v-model="email"
            type="email"
            autocomplete="username"
            required
            autofocus
            placeholder="name@booksy.com"
          />
        </label>

        <label class="field">
          <span>Password</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            placeholder="Enter your password"
          />
        </label>

        <p v-if="error" class="form-error" role="alert">{{ error }}</p>

        <button class="button" type="submit" :disabled="busy">
          {{ busy ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>

      <p class="login-note">
        Accounts are created by an admin. There is no self-registration.
      </p>
    </div>
  </div>
</template>
