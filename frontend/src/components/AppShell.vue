<template>
  <div class="shell">
    <!-- Desktop sidebar -->
    <aside class="sidebar">
      <div class="side-top"><Logo /></div>
      <nav class="side-nav">
        <router-link v-for="t in tabs" :key="t.name" :to="t.to" class="side-link" exact-active-class="active">
          <Icon :name="t.icon" /><span>{{ t.label }}</span>
        </router-link>
      </nav>
    </aside>

    <div class="main">
      <header class="topbar">
        <span class="top-logo"><Logo /></span>
        <span class="spacer"></span>
        <ThemeToggle />
      </header>
      <div v-if="offline" class="offline">You're offline. Beaver needs an internet connection to answer questions.</div>
      <main class="content" :class="{ chat: $route.name === 'ask' }"><router-view /></main>
    </div>

    <!-- Mobile bottom tabs -->
    <nav class="bottom-tabs">
      <router-link v-for="t in tabs" :key="t.name" :to="t.to" class="tab" exact-active-class="active">
        <Icon :name="t.icon" /><span>{{ t.label }}</span>
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import Logo from './Logo.vue'
import ThemeToggle from './ThemeToggle.vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { auth } from '../lib/auth'

const offline = ref(!navigator.onLine)
const setOnline = () => (offline.value = !navigator.onLine)
onMounted(() => { window.addEventListener('online', setOnline); window.addEventListener('offline', setOnline) })
onBeforeUnmount(() => { window.removeEventListener('online', setOnline); window.removeEventListener('offline', setOnline) })

const base = [
  { name: 'ask', label: 'Ask', icon: 'ask', to: '/' },
  { name: 'sheets', label: 'Sheets', icon: 'sheets', to: '/sheets' },
  { name: 'history', label: 'History', icon: 'history', to: '/history' },
  { name: 'account', label: 'Account', icon: 'account', to: '/account' }
]
const tabs = computed(() => (auth.profile?.is_admin ? [...base, { name: 'admin', label: 'Admin', icon: 'lock', to: '/admin' }] : base))
</script>

<style scoped>
.shell { min-height: 100dvh; display: flex; }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.topbar { display: flex; align-items: center; gap: 12px; padding: 12px 20px; padding-top: calc(12px + env(safe-area-inset-top)); }
.spacer { flex: 1; }
.content.chat { padding-bottom: 0; }
.offline { background: var(--danger); color: #fff; text-align: center; padding: 8px 12px; font-size: 14px; }
.content { flex: 1; padding: 8px 20px 110px; max-width: 880px; width: 100%; margin: 0 auto; }

.sidebar { display: none; }
.bottom-tabs {
  position: fixed; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-around;
  background: var(--surface); border-top: 1px solid var(--border);
  padding: 8px 8px env(safe-area-inset-bottom); height: var(--tabs-h); z-index: 10;
}
.tab { display: flex; flex-direction: column; align-items: center; gap: 3px; font-size: 11px; color: var(--faint); padding: 4px 14px; }
.tab.active { color: var(--accent); }

@media (min-width: 900px) {
  .bottom-tabs, .top-logo { display: none; }
  .content { padding-bottom: 40px; }
  .content.chat { padding-bottom: 0; }
  .sidebar { display: flex; flex-direction: column; width: 230px; border-right: 1px solid var(--border); background: var(--surface); padding: 20px 14px; position: sticky; top: 0; height: 100dvh; }
  .side-top { padding: 4px 8px 24px; }
  .side-nav { display: flex; flex-direction: column; gap: 4px; }
  .side-link { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 12px; color: var(--muted); font-weight: 500; }
  .side-link:hover { background: var(--hover); }
  .side-link.active { background: var(--hover); color: var(--text); }
}
</style>
