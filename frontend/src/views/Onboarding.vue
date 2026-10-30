<template>
  <div class="page">
    <header class="top">
      <Logo />
      <span class="spacer"></span>
      <span class="muted small">Step {{ step }} of 2</span>
      <ThemeToggle />
    </header>

    <main class="wrap">
      <template v-if="step === 1">
        <div class="eyebrow">LET’S GET YOUR DATA IN</div>
        <h1 class="h1">Add your first spreadsheet</h1>
        <p class="muted sub">You can always add more later.</p>
        <UploadPanel @continue="afterUpload" />
        <p class="skip"><router-link to="/" class="link">Skip for now</router-link></p>
      </template>

      <template v-else>
        <div class="eyebrow">ALMOST DONE</div>
        <h1 class="h1">Which currency do you use?</h1>
        <p class="muted sub">
          <template v-if="detected">We found {{ label(detected) }} in your sheet. Change it if that's wrong.</template>
          <template v-else>Beaver shows money amounts with this symbol.</template>
        </p>
        <div class="options">
          <button v-for="c in currencies" :key="c.code" class="card opt" :class="{ on: currency === c.code }"
                  @click="currency = c.code">
            <span class="sym">{{ c.symbol }}</span>
            <span>{{ c.name }}</span>
          </button>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="btn btn-primary save" :disabled="saving" @click="finish">{{ saving ? 'Saving…' : 'Finish' }}</button>
      </template>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import Logo from '../components/Logo.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import UploadPanel from '../components/UploadPanel.vue'
import { auth, loadProfile } from '../lib/auth'
import { supabase } from '../lib/supabase'

const router = useRouter()
const step = ref(1)
const detected = ref(null)
const currency = ref(auth.profile?.currency || 'USD')
const saving = ref(false)
const error = ref('')

const currencies = [
  { code: 'NGN', symbol: '₦', name: 'Nigerian naira' },
  { code: 'USD', symbol: '$', name: 'US dollar' },
  { code: 'EUR', symbol: '€', name: 'Euro' },
  { code: 'GBP', symbol: '£', name: 'British pound' }
]
const label = (code) => currencies.find((c) => c.code === code)?.name || code

function afterUpload(result) {
  detected.value = result.detected_currency
  if (result.detected_currency) currency.value = result.detected_currency
  step.value = 2
}

async function finish() {
  saving.value = true
  error.value = ''
  const { error: e } = await supabase.from('profiles').update({ currency: currency.value }).eq('id', auth.user.id)
  saving.value = false
  if (e) return (error.value = 'Could not save your currency. Please try again.')
  await loadProfile()
  router.replace('/')
}
</script>

<style scoped>
.page { min-height: 100dvh; padding: 0 16px 40px; }
.top { display: flex; align-items: center; gap: 14px; max-width: 960px; margin: 0 auto; padding: 16px 0; padding-top: calc(16px + env(safe-area-inset-top)); }
.spacer { flex: 1; }
.small { font-size: 14px; }
.wrap { max-width: 960px; margin: 24px auto 0; }
.eyebrow { font-size: 12px; letter-spacing: 0.14em; font-weight: 700; color: var(--gold); text-align: center; }
.h1 { text-align: center; margin-top: 10px; }
.sub { text-align: center; margin: 0 0 28px; }
.skip { text-align: center; margin-top: 22px; }
.options { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; max-width: 640px; margin: 0 auto; }
.opt { display: flex; align-items: center; gap: 12px; padding: 16px; cursor: pointer; color: var(--text); font-size: 16px; text-align: left; font-family: inherit; }
.opt.on { border-color: var(--accent); background: var(--hover); }
.sym { font-size: 22px; font-weight: 700; width: 30px; }
.save { display: flex; margin: 26px auto 0; min-width: 200px; }
.error { color: var(--danger); text-align: center; }
</style>
