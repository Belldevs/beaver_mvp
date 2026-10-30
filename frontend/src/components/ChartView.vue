<template>
  <div class="chart">
    <div v-if="chart.ranges" class="range">
      <button v-for="r in ranges" :key="r.n" type="button" :class="{ on: n === r.n }" @click="n = r.n">{{ r.label }}</button>
    </div>

    <!-- Donut (share) -->
    <div v-if="kind === 'pie'" class="pie">
      <svg class="donut" viewBox="0 0 42 42" role="img" :aria-label="ariaLabel">
        <circle class="ring" cx="21" cy="21" r="15.9155" />
        <circle
          v-for="s in slices" :key="s.i" class="slice" cx="21" cy="21" r="15.9155"
          :stroke="s.color" :stroke-dasharray="`${s.len} ${100 - s.len}`" :stroke-dashoffset="s.offset"
        />
      </svg>
      <ul class="legend">
        <li v-for="s in slices" :key="s.i">
          <span class="sw" :style="{ background: s.color }"></span>
          <span class="nm" :title="s.label">{{ s.label }}</span>
          <span class="vl">{{ short(s.value) }}</span>
          <span class="pc">{{ s.share.toFixed(1) }}%</span>
        </li>
      </ul>
    </div>

    <!-- Line (trend) -->
    <div v-else-if="kind === 'line'" class="line" role="img" :aria-label="ariaLabel">
      <div class="plotline">
        <svg class="lsvg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <line
            v-for="s in segs" :key="s.i" :x1="s.x1" :y1="s.y1" :x2="s.x2" :y2="s.y2"
            :stroke="s.color" vector-effect="non-scaling-stroke"
          />
        </svg>
        <template v-for="(p, i) in pts" :key="i">
          <span class="dot" :class="{ hi: i === hi }" :style="{ left: p.x + '%', top: p.y + '%', background: p.color }"></span>
          <span v-if="showVal(i)" class="pv" :style="{ left: p.x + '%', top: p.y + '%' }">{{ short(values[i]) }}</span>
        </template>
      </div>
      <div class="xl">
        <span v-for="(l, i) in labels" :key="i" :class="{ off: !showLab(i) }">{{ l }}</span>
      </div>
    </div>

    <!-- Bars (default; also handles negative values and a reference marker) -->
    <template v-else>
      <div class="bars" role="img" :aria-label="ariaLabel">
        <div v-for="(v, i) in values" :key="i" class="col">
          <span class="val">{{ short(v) }}</span>
          <div class="plot">
            <div v-if="hasNeg" class="zero" :style="{ bottom: pos(0) + '%' }"></div>
            <div class="bar" :style="barStyle(v, i)"></div>
            <div v-if="refs[i] != null" class="ref" :style="{ bottom: pos(refs[i]) + '%' }"></div>
          </div>
          <span class="lab" :title="labels[i]">{{ labels[i] }}</span>
        </div>
      </div>
      <p v-if="hasRefs" class="note"><span class="ref-sw"></span> Reorder level</p>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { compact } from '../lib/format'

const props = defineProps({
  chart: { type: Object, required: true },
  currency: { type: String, default: 'USD' }
})

const FALLBACKS = ['#111827', '#374151', '#6B7280', '#9CA3AF', '#D1D5DB', '#E5E7EB', '#F3F4F6']
const ranges = [{ n: 6, label: '6M' }, { n: 3, label: '3M' }, { n: 1, label: '1M' }]
const n = ref(6)

const kind = computed(() => (props.chart.type === 'line' || props.chart.type === 'pie' ? props.chart.type : 'bar'))
const windowed = computed(() => !!props.chart.ranges)
const win = (arr) => (Array.isArray(arr) ? (windowed.value ? arr.slice(-Math.max(n.value, 2)) : arr) : [])

const values = computed(() => win(props.chart.values))
const labels = computed(() => win(props.chart.labels))
const colors = computed(() => (props.chart.colors ? win(props.chart.colors) : null))
const refs = computed(() => win(props.chart.reference))
const hasRefs = computed(() => refs.value.some((r) => r != null))
const hi = computed(() => (windowed.value ? values.value.length - 1 : props.chart.highlight ?? -1))

// Negative numbers must not become "₦-1.2K", so the sign goes first.
const short = (v) => (Number(v) < 0 ? '-' : '') + compact(Math.abs(Number(v) || 0), props.chart.format, props.currency)

const ariaLabel = computed(() => labels.value.map((l, i) => `${l}: ${short(values.value[i])}`).join(', '))

function colorAt(i) {
  return colors.value?.[i] || props.chart.color || (i === hi.value ? 'var(--accent)' : 'var(--hover)')
}

/* ---------- bars ---------- */
const lo = computed(() => Math.min(0, ...values.value, ...refs.value.filter((r) => r != null)))
const top = computed(() => Math.max(0, ...values.value, ...refs.value.filter((r) => r != null)))
const span = computed(() => top.value - lo.value || 1)
const hasNeg = computed(() => lo.value < 0)
const pos = (v) => ((v - lo.value) / span.value) * 100

function barStyle(v, i) {
  const h = v === 0 ? 0 : Math.max((Math.abs(v) / span.value) * 100, 1.5)
  const bottom = v >= 0 ? pos(0) : pos(0) - h
  // With no per-bar colours, a single colour is dimmed except for the highlighted bar.
  const dim = !colors.value && props.chart.color && i !== hi.value
  const fill = colors.value?.[i] || (i === hi.value ? props.chart.color || 'var(--accent)' : props.chart.color || 'var(--hover)')
  return {
    bottom: bottom + '%',
    height: h + '%',
    background: fill,
    opacity: dim ? 0.55 : 1,
    borderRadius: v < 0 ? '0 0 6px 6px' : '6px 6px 0 0'
  }
}

/* ---------- line ---------- */
const vmin = computed(() => Math.min(...values.value))
const vmax = computed(() => Math.max(...values.value))
const pts = computed(() => {
  const v = values.value
  const count = v.length
  const range = vmax.value - vmin.value || 1
  return v.map((val, i) => ({
    x: ((i + 0.5) / count) * 100,
    y: 24 + (1 - (val - vmin.value) / range) * 60, // keeps room above for value labels
    color: colors.value?.[i] || props.chart.color || 'var(--accent)'
  }))
})
const segs = computed(() =>
  pts.value.slice(1).map((p, k) => ({ i: k, x1: pts.value[k].x, y1: pts.value[k].y, x2: p.x, y2: p.y, color: p.color }))
)
// With many points, label only the latest, the highest and the lowest, and every other month on the axis.
const showVal = (i) => values.value.length <= 7 || i === hi.value || values.value[i] === vmax.value || values.value[i] === vmin.value
const showLab = (i) => values.value.length <= 7 || (values.value.length - 1 - i) % 2 === 0

/* ---------- donut ---------- */
const slices = computed(() => {
  if (kind.value !== 'pie') return []
  const vals = values.value.map((v) => Math.max(0, Number(v) || 0))
  const total = vals.reduce((a, b) => a + b, 0) || 1
  const given = props.chart.shares
  const shares = Array.isArray(given) && given.length === vals.length ? given.map(Number) : vals.map((v) => (v / total) * 100)
  let acc = 0
  return vals.map((v, i) => {
    const share = shares[i] || 0
    const s = {
      i, label: labels.value[i], value: v, share,
      color: colors.value?.[i] || FALLBACKS[Math.min(i, FALLBACKS.length - 1)],
      len: Math.max(0, share - (vals.length > 1 ? 0.5 : 0)), // hairline gap between slices
      offset: 25 - acc // 25 starts the first slice at 12 o'clock
    }
    acc += share
    return s
  })
})
</script>

<style scoped>
.chart { margin-top: 18px; padding: 4px 0 0; }
.range { display: flex; justify-content: flex-end; gap: 2px; margin-bottom: 8px; }
.range button { border: 0; background: transparent; color: var(--faint); padding: 3px 9px; border-radius: 99px; font: inherit; font-size: 12px; cursor: pointer; }
.range button.on { background: var(--hover); color: var(--text); }

/* bars */
.bars { display: flex; align-items: stretch; gap: 8px; height: 180px; overflow-x: auto; }
.col { flex: 1; min-width: 44px; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.plot { flex: 1; width: 100%; position: relative; }
.bar { position: absolute; left: 0; right: 0; }
.zero { position: absolute; left: 0; right: 0; height: 1px; background: var(--border); }
.ref { position: absolute; left: -2px; right: -2px; height: 0; border-top: 2px dashed var(--text); opacity: 0.8; }
.val, .lab { font-size: 11px; color: var(--faint); white-space: nowrap; max-width: 70px; overflow: hidden; text-overflow: ellipsis; }
.col .val { color: var(--muted); }
.note { display: flex; align-items: center; gap: 6px; margin: 8px 0 0; font-size: 12px; color: var(--faint); }
.ref-sw { width: 16px; height: 0; border-top: 2px dashed var(--text); opacity: 0.8; }

/* line */
.plotline { position: relative; height: 150px; }
.lsvg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.lsvg line { stroke-width: 2.5; stroke-linecap: round; }
.dot { position: absolute; width: 9px; height: 9px; border-radius: 50%; transform: translate(-50%, -50%); border: 2px solid var(--bg); box-sizing: content-box; }
.dot.hi { width: 11px; height: 11px; }
.pv { position: absolute; transform: translate(-50%, -150%); font-size: 11px; color: var(--muted); white-space: nowrap; }
.xl { display: flex; margin-top: 6px; }
.xl span { flex: 1; min-width: 0; text-align: center; font-size: 11px; color: var(--faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.xl span.off { visibility: hidden; }

/* donut */
.pie { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; }
.donut { width: 150px; height: 150px; flex: none; transform: none; }
.ring, .slice { fill: none; stroke-width: 6; }
.ring { stroke: var(--hover); }
.legend { list-style: none; margin: 0; padding: 0; flex: 1; min-width: 180px; display: flex; flex-direction: column; gap: 8px; }
.legend li { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
.sw { width: 10px; height: 10px; border-radius: 3px; flex: none; }
.nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.vl { color: var(--faint); white-space: nowrap; }
.pc { width: 46px; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>