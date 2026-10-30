<template>
  <div class="auth-page">
    <header class="auth-top">
      <Logo />
      <span class="spacer"></span>
      <span class="muted switch">
        <template v-if="isSignup">Already have an account? <router-link to="/login" class="link">Log in</router-link></template>
        <template v-else>New here? <router-link to="/signup" class="link">Create account</router-link></template>
      </span>
      <ThemeToggle />
    </header>

    <div class="card auth-card">
      <div class="eyebrow">{{ isSignup ? 'GET STARTED FREE' : 'WELCOME BACK' }}</div>
      <h1 class="h1">{{ isSignup ? 'Create your account' : 'Log in to Beaver' }}</h1>
      <p v-if="isSignup" class="muted">No credit card needed. Your first 25 questions are free.</p>


      <div class="form">
        <label>Email address
          <input v-model.trim="email" type="email" autocomplete="email" placeholder="you@company.com" />
        </label>
        <label>Password
          <input v-model="password" type="password" :autocomplete="isSignup ? 'new-password' : 'current-password'"
                 placeholder="At least 8 characters" @keyup.enter="submit" />
        </label>

        <p v-if="error" class="msg error">{{ error }}</p>
        <p v-if="info" class="msg info">{{ info }}</p>

        <button class="btn btn-primary wide" :disabled="busy" @click="submit">
          {{ busy ? 'Please wait…' : isSignup ? 'Create account' : 'Log in' }}
        </button>
      </div>

      <p v-if="isSignup" class="muted terms">By continuing, you agree to our Terms and Privacy Policy.</p>
      <p class="muted terms"><Icon name="lock" class="lock" /> Your data is private to your account</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Logo from '../components/Logo.vue'
import Icon from '../components/Icon.vue'
import ThemeToggle from '../components/ThemeToggle.vue'


const route = useRoute()
const router = useRouter()
const isSignup = computed(() => route.meta.mode === 'signup')

const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const info = ref('')



async function submit() {
  error.value = ''
  info.value = ''
  if (!/^\S+@\S+\.\S+$/.test(email.value)) return (error.value = 'Please enter a valid email address.')
  if (password.value.length < 8) return (error.value = 'Password must be at least 8 characters.')

  busy.value = true
  try {
    if (isSignup.value) {
      const { data, error: e } = await signUpWithEmail(email.value, password.value)
      if (e) throw e
      if (!data.session) info.value = 'Check your email to confirm your account, then log in.'
      else router.replace('/')
    } else {
      const { error: e } = await signInWithEmail(email.value, password.value)
      if (e) throw e
      router.replace('/')
    }
  } catch (e) {
    error.value = e.message || 'Something went wrong. Please try again.'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.auth-page { min-height: 100dvh; padding: 0 16px 40px; }
.auth-top { display: flex; align-items: center; gap: 14px; max-width: 520px; margin: 0 auto; padding: 16px 0; padding-top: calc(16px + env(safe-area-inset-top)); }
.spacer { flex: 1; }
.switch { font-size: 14px; }
.auth-card { max-width: 520px; margin: 12px auto 0; padding: 28px 24px; display: flex; flex-direction: column; gap: 14px; }
.eyebrow { font-size: 12px; letter-spacing: 0.14em; font-weight: 700; color: var(--gold); }
.auth-card .h1 { margin: 0; }
.auth-card p { margin: 0; }
.wide { width: 100%; }
.g { font-weight: 800; color: #4285f4; margin-right: 6px; }
.divider { display: flex; align-items: center; gap: 12px; color: var(--muted); font-size: 14px; }
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.form { display: flex; flex-direction: column; gap: 14px; }
label { display: flex; flex-direction: column; gap: 6px; font-weight: 600; font-size: 14px; }
.msg { font-size: 14px; }
.error { color: var(--danger); }
.info { color: var(--success); }
.terms { font-size: 13px; text-align: center; }
.lock { width: 14px; height: 14px; vertical-align: -2px; color: var(--success); }
</style>
