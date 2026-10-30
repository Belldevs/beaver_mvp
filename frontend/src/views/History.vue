<template>
  <section class="page">
    <h1 class="h1">History</h1>
    <p class="muted">Tap a question to reopen its answer. Reopening is free.</p>
    <div v-if="loading" class="card pad muted">Loading…</div>
    <div v-else-if="!items.length" class="card pad muted">No questions yet. Ask one on the Ask tab.</div>
    <div v-for="a in items" :key="a.id" class="item">
      <button class="row card" @click="toggle(a)">
        <span class="qt">{{ a.question }}</span>
        <span class="muted small">{{ timeAgo(a.created_at) }}</span>
      </button>
      <AnswerCard v-if="openId === a.id" :card="a.card" @ask="askAgain" />
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AnswerCard from '../components/AnswerCard.vue'
import { ask } from '../lib/ask'
import { timeAgo } from '../lib/files'
import { supabase } from '../lib/supabase'

const router = useRouter()
const items = ref([])
const loading = ref(true)
const openId = ref(null)
const toggle = (a) => (openId.value = openId.value === a.id ? null : a.id)
function askAgain(q) {
  ask(q)
  router.push('/')
}
onMounted(async () => {
  const { data } = await supabase.from('answers').select('id,question,card,created_at').order('created_at', { ascending: false }).limit(100)
  items.value = data || []
  loading.value = false
})
</script>

<style scoped>
.page { padding-top: 12px; }
.pad { padding: 16px; margin-top: 14px; }
.item { margin-top: 10px; }
.row { width: 100%; display: flex; justify-content: space-between; gap: 12px; padding: 14px 16px; text-align: left; font: inherit; color: var(--text); cursor: pointer; }
.qt { font-weight: 500; }
.small { font-size: 13px; white-space: nowrap; }
</style>
