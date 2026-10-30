<template>
  <section class="page">
    <h1 class="h1">Account</h1>
    <div class="card box">
      <div class="r"><span class="muted">Email</span><strong>{{ auth.user?.email }}</strong></div>
      <div class="r"><span class="muted">Free questions</span><strong>{{ auth.profile?.questions_used ?? 0 }} of 25 used</strong></div>
      <label class="r">
        <span class="muted">Currency</span>
        <select v-model="currency" @change="saveCurrency">
          <option v-for="c in currencies" :key="c" :value="c">{{ c }}</option>
        </select>
      </label>
      <div class="r"><span class="muted">Theme</span><ThemeToggle /></div>
      <p v-if="saved" class="muted small">Saved.</p>
    </div>
    <button class="btn btn-outline out" @click="logout">Log out</button>
  </section>
</template>

<script setup>
import { ref, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import ThemeToggle from '../components/ThemeToggle.vue'
import { auth, signOut } from '../lib/auth'
import { supabase } from '../lib/supabase'

const router = useRouter()
const currencies = ['NGN', 'USD', 'EUR', 'GBP']
const currency = ref('USD')
const saved = ref(false)
watchEffect(() => { if (auth.profile?.currency) currency.value = auth.profile.currency })

async function saveCurrency() {
  const { error } = await supabase.from('profiles').update({ currency: currency.value }).eq('id', auth.user.id)
  if (!error) { auth.profile.currency = currency.value; saved.value = true }
}
async function logout() { await signOut(); router.replace('/login') }
</script>

<style scoped>
.page { padding-top: 12px; }
.box { padding: 6px 18px; margin: 18px 0; }
.r { display: flex; justify-content: space-between; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--border); gap: 12px; }
.r:last-of-type { border-bottom: 0; }
select { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px; font: inherit; }
.small { font-size: 13px; }
</style>
