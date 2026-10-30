<template>
  <div class="meter">
    <div class="row">
      <span class="muted small">Storage</span>
      <strong class="small">{{ formatBytes(usedBytes) }} of 10 MB used</strong>
    </div>
    <div class="bar"><div class="fill" :class="{ warn: pct > 90 }" :style="{ width: pct + '%' }"></div></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { LIMIT_BYTES, formatBytes, usedBytes } from '../lib/files'

const pct = computed(() => Math.min(100, (usedBytes.value / LIMIT_BYTES) * 100))
</script>

<style scoped>
.row { display: flex; justify-content: space-between; margin-bottom: 8px; }
.small { font-size: 13px; }
.bar { height: 8px; background: var(--hover); border-radius: 99px; overflow: hidden; }
.fill { height: 100%; background: var(--accent); border-radius: 99px; transition: width 0.3s; }
.fill.warn { background: var(--danger); }
</style>
