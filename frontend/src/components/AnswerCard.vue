<template>
  <article class="answer">
    <div class="head">
      <span class="title">{{ card.title }}</span>
      <span v-if="card.sheet" class="src">Source: {{ card.sheet }}</span>
    </div>

    <p v-if="card.kind === 'message' || card.kind === 'empty'" class="text">{{ card.message }}</p>

    <template v-else>
      <!-- Headline. For reports it carries the tone colour and label. -->
      <div v-if="card.headline || toneLabel" class="headline" :class="{ toned: isReport && card.color }" :style="isReport && card.color ? { '--tone': card.color } : null">
        <span v-if="toneLabel" class="tone-pill">{{ toneLabel }}</span>
        <div v-if="showBig" class="big">
          <template v-if="!isReport && card.headline.text">{{ card.headline.text }}</template>
          <template v-else>{{ fmt(card.headline.value, card.headline.format, cur) }}</template>
          <span v-if="card.headline.suffix" class="suffix">{{ card.headline.suffix }}</span>
        </div>
        <div v-if="subLine" class="muted sub">{{ subLine }}</div>
      </div>

      <div v-if="card.change" class="badge" :class="card.change.direction">
        <span>{{ card.change.direction === 'up' ? '▲' : card.change.direction === 'down' ? '▼' : '■' }}</span>
        <b v-if="card.change.pct != null">{{ card.change.pct > 0 ? '+' : '' }}{{ card.change.pct }}%</b>
        <b v-else>{{ fmt(card.change.amount, card.change.format, cur) }}</b>
        <span class="muted">vs. {{ card.change.vs }}</span>
      </div>
      <p v-if="card.change && card.change.pct != null && card.change.previous != null" class="muted sub">
        {{ card.change.amount >= 0 ? 'Up' : 'Down' }} {{ fmt(Math.abs(card.change.amount), card.change.format, cur) }}
        (was {{ fmt(card.change.previous, card.change.format, cur) }}).
      </p>

      <p v-if="card.headline_text && card.headline_text !== card.title" class="lead"><RichText :text="card.headline_text" /></p>
      <p v-if="card.text" class="text"><RichText :text="card.text" /></p>

      <!-- Things to watch -->
      <div v-if="card.watch && card.watch.length" class="watch">
        <span class="label">Watch</span>
        <ul><li v-for="(w, i) in card.watch" :key="i"><RichText :text="w" /></li></ul>
      </div>

      <!-- Simple cards: one chart and/or one table -->
      <ChartView v-if="card.chart" :chart="card.chart" :currency="cur" />
      <DataTable v-if="card.table" :table="card.table" :currency="cur" />

      <!-- Report cards: one block per section -->
      <div v-if="isReport && card.sections && card.sections.length" class="sections">
        <section v-for="s in card.sections" :key="s.id" class="sec" :style="{ '--tone': s.color || '#9CA3AF' }">
          <h3 class="sec-title"><span class="dot"></span>{{ s.title }}</h3>
          <p v-if="s.text" class="text sec-text"><RichText :text="s.text" /></p>
          <ChartView v-if="s.chart" :chart="s.chart" :currency="cur" />
          <DataTable v-if="s.table" :table="s.table" :currency="cur" />
        </section>
      </div>

      <div v-if="card.takeaways && card.takeaways.length" class="take">
        <span class="label">Key takeaways</span>
        <ul><li v-for="(t, i) in card.takeaways" :key="i"><RichText :text="t" /></li></ul>
      </div>

      <div v-if="card.followups && card.followups.length" class="follow">
        <span class="label">Related</span>
        <div class="chips">
          <button v-for="f in card.followups" :key="f" class="chip" @click="$emit('ask', f)">{{ f }}</button>
        </div>
      </div>

      <button v-if="card.steps && card.steps.length" class="assume" @click="open = !open">
        {{ open ? 'Hide assumptions' : 'View assumptions' }}
      </button>
      <ol v-if="open" class="steps">
        <li v-for="(s, i) in card.steps" :key="i">{{ s }}</li>
        <li class="muted">All numbers were calculated in code from your sheet. The AI only wrote the explanation.</li>
      </ol>
    </template>
  </article>
</template>

<script setup>
import { computed, ref } from 'vue'
import ChartView from './ChartView.vue'
import DataTable from './DataTable.vue'
import RichText from './RichText.vue'
import { fmt } from '../lib/format'

const props = defineProps({ card: { type: Object, required: true } })
defineEmits(['ask'])

const cur = computed(() => props.card.currency || 'USD')
const open = ref(false)
const isReport = computed(() => props.card.kind === 'report')

const TONE_LABELS = { positive: 'Looking good', negative: 'Needs attention', watch: 'Worth watching' }
const toneLabel = computed(() => (isReport.value ? TONE_LABELS[props.card.tone] || '' : ''))

// Reports with no date column send {value: null}: show no big number then.
const showBig = computed(() => {
  const h = props.card.headline
  if (!h) return false
  return isReport.value ? h.value != null : true
})

// Ranking cards: big = name, small = value. Reports: big = value, small = the month it describes.
const subLine = computed(() => {
  const h = props.card.headline
  if (!h || !h.text) return ''
  return isReport.value ? h.text : fmt(h.value, h.format, cur.value)
})
</script>

<style scoped>
.answer { margin-top: 18px; }
.head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.title { font-size: 13px; font-weight: 500; color: var(--muted); }
.src { color: var(--faint); font-size: 12px; }

.headline.toned { border-left: 4px solid var(--tone); padding-left: 14px; }
.tone-pill { display: inline-block; margin-bottom: 6px; padding: 2px 10px; border-radius: 99px; font-size: 12px; font-weight: 500; color: var(--tone); background: color-mix(in srgb, var(--tone) 14%, transparent); }
.big { font-size: clamp(34px, 9vw, 48px); font-weight: 600; letter-spacing: -0.035em; line-height: 1.1; color: var(--text); }
.suffix { font-size: 15px; font-weight: 400; margin-left: 8px; color: var(--faint); }
.sub { margin: 6px 0 0; font-size: 13px; color: var(--faint); }
.lead { margin: 14px 0 0; font-size: 16px; font-weight: 500; line-height: 1.45; color: var(--text); }
.text { line-height: 1.6; margin: 14px 0; font-size: 15px; font-weight: 400; color: var(--muted); }
.badge { display: inline-flex; gap: 6px; align-items: center; margin-top: 12px; padding: 4px 10px; border-radius: 99px; background: var(--hover); font-size: 13px; }
.badge b { font-weight: 600; }
.badge .muted { color: var(--faint); }
.badge.up b, .badge.up span:first-child { color: var(--success); }
.badge.down b, .badge.down span:first-child { color: var(--danger); }

.watch { margin: 16px 0 0; padding: 12px 14px; border-left: 3px solid #F97316; border-radius: 0 10px 10px 0; background: color-mix(in srgb, #F97316 10%, transparent); }
.watch ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.55; font-size: 14px; color: var(--text); }

.sections { margin-top: 8px; }
.sec { margin-top: 26px; padding-left: 14px; border-left: 3px solid var(--tone); }
.sec-title { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 15px; font-weight: 600; color: var(--text); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--tone); flex: none; }
.sec-text { margin: 8px 0 0; font-size: 14px; }

.label { display: block; font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--faint); font-weight: 500; }
.take { margin-top: 20px; }
.take ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.6; font-size: 14px; color: var(--muted); }
.follow { margin-top: 20px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.chip { border: 1px solid var(--border); background: transparent; color: var(--muted); padding: 7px 12px; border-radius: 99px; font: inherit; font-size: 13px; cursor: pointer; text-align: left; }
.chip:hover { background: var(--hover); color: var(--text); }
.assume { margin-top: 16px; background: none; border: 0; color: var(--faint); font: inherit; font-size: 13px; cursor: pointer; padding: 0; text-decoration: underline; text-underline-offset: 3px; }
.assume:hover { color: var(--muted); }
.steps { margin: 10px 0 0; padding-left: 20px; line-height: 1.6; font-size: 13px; color: var(--muted); }
.steps .muted { color: var(--faint); }
</style>