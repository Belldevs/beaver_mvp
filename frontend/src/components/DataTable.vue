<template>
  <div class="table-wrap">
    <table>
      <thead><tr><th v-for="c in table.columns" :key="c.key">{{ c.label }}</th></tr></thead>
      <tbody>
        <tr v-for="(r, i) in table.rows" :key="i">
          <td v-for="c in table.columns" :key="c.key" :class="tone(c, r[c.key])">
            <span v-if="c.key === 'status'" class="pill-low">{{ r[c.key] }}</span>
            <template v-else>{{ cell(c, r[c.key]) }}</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { fmt } from '../lib/format'

const props = defineProps({
  table: { type: Object, required: true },
  currency: { type: String, default: 'USD' }
})

// The backend sends formatted strings for some columns (e.g. "+3.2%") and raw numbers for others.
function cell(c, v) {
  if (v === null || v === undefined || v === '') return '-'
  return c.format && typeof v === 'number' ? fmt(v, c.format, props.currency) : v
}

// Colour change columns: green for up, red for down.
function tone(c, v) {
  if (c.key !== 'change' && c.key !== 'pct') return ''
  if (typeof v === 'number') return v > 0 ? 'pos' : v < 0 ? 'neg' : ''
  if (typeof v === 'string') {
    if (/^\+\d/.test(v)) return 'pos'
    if (/^[-\u2212]\d/.test(v)) return 'neg'
  }
  return ''
}
</script>

<style scoped>
.table-wrap { overflow-x: auto; margin-top: 14px; border-top: 1px solid var(--border); }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 10px 12px 10px 0; border-bottom: 1px solid var(--border); white-space: nowrap; color: var(--muted); }
td:first-child { color: var(--text); }
th { color: var(--faint); font-weight: 500; font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase; }
tr:last-child td { border-bottom: 0; }
td.pos { color: var(--success); }
td.neg { color: var(--danger); }
.pill-low { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); padding: 2px 10px; border-radius: 99px; font-size: 12px; }
</style>