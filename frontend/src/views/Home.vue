<template>
  <section class="home">
    <!-- Idle: greeting + suggestions. Disappears as soon as a conversation starts. -->
    <div v-if="!thread.length" class="hero">
      <p class="greeting">{{ greeting }}, {{ name }}</p>
      <h1 class="h1">What can Beaver help with?</h1>

      <div v-if="!allSheets.length" class="empty">
        <p class="muted">Upload an Excel or CSV file, or link a Google Sheet, to start.</p>
        <router-link to="/onboarding" class="btn btn-primary"><Icon name="plus" /> Add your first sheet</router-link>
      </div>

      <template v-else>
        <div class="chips">
          <button v-for="s in suggestions" :key="s" class="chip" @click="submit(s)">{{ s }}</button>
        </div>

        <div class="sheets">
          <div class="sheets-head">
            <span>Connected sheets</span>
            <router-link to="/sheets">Manage</router-link>
          </div>
          <div v-for="s in allSheets" :key="s.id" class="sheet">
            <Icon name="sheets" />
            <span class="name">{{ s.name }}</span>
            <span class="meta">{{ s.row_count.toLocaleString() }} rows · {{ timeAgo(s.created_at) }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- Conversation: oldest on top, newest at the bottom. -->
    <div v-else ref="threadEl" class="thread">
      <div v-for="t in thread" :key="t.id" class="turn">
        <div class="q">{{ t.q }}</div>
        <div v-if="t.status === 'loading'" class="progress">
          <div v-for="(label, i) in STAGES" v-show="i <= t.stage" :key="label" class="step" :class="{ done: i < t.stage }">
            <span class="mark"><Icon v-if="i < t.stage" name="check" /><span v-else class="dots"><i></i><i></i><i></i></span></span>
            {{ label }}
          </div>
          <p v-if="t.waking" class="wake">Waking Beaver up… the first question after a quiet spell can take up to a minute.</p>
        </div>
        <div v-else-if="t.status === 'error'" class="status error">{{ t.error }}</div>
        <AnswerCard v-else :card="t.card" @ask="submit" />
      </div>
    </div>

    <!-- Input + send are docked at the bottom. -->
    <div class="composer">
      <form class="ask-box" @submit.prevent="submit()">
        <input v-model="text" class="ask-input" :disabled="!allSheets.length" placeholder="Ask about your spreadsheets…" />
        <button class="send" :disabled="!text.trim() || !allSheets.length" aria-label="Send"><Icon name="send" /></button>
      </form>
      <p class="usage">{{ used }} of {{ LIMIT }} free questions used</p>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import AnswerCard from '../components/AnswerCard.vue'
import { ask, STAGES, thread } from '../lib/ask'
import { auth } from '../lib/auth'
import { allSheets, loadFiles, timeAgo } from '../lib/files'

const LIMIT = 25
const text = ref('')
const threadEl = ref(null)
const suggestions = ['What is our total inventory value?', 'Which products are running low in stock?', 'How did sales compare to last month?']

function submit(q) {
  const question = (typeof q === 'string' ? q : text.value).trim()
  if (!question) return
  text.value = ''
  ask(question)
}
const used = computed(() => auth.profile?.questions_used ?? 0)

// Bring the newest question to the top of the screen so it (and its answer) is what you see.
function showLatest(smooth) {
  nextTick(() => {
    const last = threadEl.value?.lastElementChild
    if (last) last.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
  })
}
watch(() => thread.length, () => showLatest(true))
onMounted(() => {
  loadFiles()
  if (thread.length) showLatest(false)
})

const name = computed(() => {
  const m = auth.user?.user_metadata
  const full = m?.full_name || m?.name
  if (full) return full.split(' ')[0]
  return (auth.user?.email || 'there').split('@')[0]
})

const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
})
</script>

<style scoped>
.home { display: flex; flex-direction: column; min-height: calc(100dvh - 72px); padding-bottom: calc(var(--tabs-h) + 12px); }

/* idle */
.hero { padding-top: 8vh; }
.greeting { margin: 0 0 6px; font-size: 14px; color: var(--faint); }
.empty { margin-top: 20px; display: flex; flex-direction: column; align-items: flex-start; gap: 14px; }
.chips { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; margin-top: 22px; }
.chip { border: 1px solid #555; background:transparent; color: var(--muted); padding: 9px 14px; border-radius: 99px; font: inherit; font-size: 14px; cursor: pointer; text-align: left; }
.chip:hover { background: var(--hover); color: var(--text); }
.sheets { margin-top: 44px; }
.sheets-head { display: flex; justify-content: space-between; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--faint); margin-bottom: 6px; }
.sheets-head a:hover { color: var(--muted); }
.sheet { display: flex; align-items: center; gap: 10px; padding: 8px 0; color: var(--faint); }
.sheet svg { width: 16px; height: 16px; flex: none; }
.sheet .name { color: var(--muted); font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.sheet .meta { margin-left: auto; font-size: 12px; white-space: nowrap; }

/* conversation */
.thread { padding-top: 8px; }
.turn { scroll-margin-top: 12px; margin-bottom: 36px; }
.q { margin-left: auto; width: fit-content; max-width: 88%; background: var(--hover); color: var(--text); padding: 9px 14px; border-radius: 16px 16px 4px 16px; font-size: 15px; line-height: 1.4; }
.status { margin-top: 18px; font-size: 14px; color: var(--faint); }
.status.error { color: var(--danger); }
.progress { margin-top: 18px; display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
.step { display: flex; align-items: center; gap: 10px; color: var(--text); animation: rise 0.25s ease-out; }
.step.done { color: var(--faint); }
.mark { width: 16px; height: 16px; display: grid; place-items: center; flex: none; }
.mark svg { width: 14px; height: 14px; color: var(--success); }
.wake { margin: 6px 0 0 26px; font-size: 12px; color: var(--faint); max-width: 38ch; line-height: 1.5; }
@keyframes rise { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.dots { display: inline-flex; gap: 4px; }
.dots i { width: 5px; height: 5px; border-radius: 50%; background: var(--faint); animation: pulse 1.2s infinite ease-in-out; }
.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes pulse { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }

/* docked composer */
.composer { position: sticky; bottom: calc(var(--tabs-h) + 12px); margin-top: auto; padding-top: 28px; background: linear-gradient(to top, var(--bg) 70%, transparent); z-index: 5; }
.ask-box { display: flex; gap: 8px; align-items: center; padding: 6px 6px 6px 18px; background: var(--surface); border: 1px solid var(--border); border-radius: 99px; }
.ask-box:focus-within { border-color: var(--faint); }
.ask-input { flex: 1; min-width: 0; padding: 8px 0; background: transparent; border: 0; border-radius: 0; color: var(--text); font-size: 16px; outline: none; }
.ask-input::placeholder { color: var(--faint); }
.send { width: 38px; height: 38px; border-radius: 50%; border: 0; background: var(--accent); color: #fff; display: grid; place-items: center; flex: none; cursor: pointer; }
.send svg { width: 18px; height: 18px; }
.send:disabled { background: var(--hover); color: var(--faint); cursor: default; }
.usage { margin: 8px 0 0; text-align: center; font-size: 12px; color: var(--faint); }
</style>
