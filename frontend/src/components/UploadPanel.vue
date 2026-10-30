<template>
  <div>
    <div class="grid">
      <div class="card drop" :class="{ over, busy }" @dragover.prevent="over = true" @dragleave="over = false"
           @drop.prevent="onDrop">
        <div class="ico"><Icon name="upload" /></div>
        <h3>Drop Excel or CSV here</h3>
        <p class="muted small">.xlsx or .csv · up to 10 MB</p>
        <button class="btn btn-outline" :disabled="busy" @click="picker.click()">Browse files</button>
        <input ref="picker" type="file" accept=".xlsx,.csv" hidden @change="onPick" />
      </div>

      <div class="or muted">or</div>

      <div class="card link">
        <div class="ico"><Icon name="sheets" /></div>
        <h3>Paste a Google Sheet link</h3>
        <div class="link-row">
          <input v-model.trim="url" placeholder="https://docs.google.com/spreadsheets/…" :disabled="busy"
                 @keyup.enter="submitLink" />
          <button class="go" :disabled="busy || !url" aria-label="Add Google Sheet" @click="submitLink">
            <Icon name="chevron" />
          </button>
        </div>
        <p class="muted small">The sheet must be shared as “anyone with the link can view”.</p>
      </div>
    </div>

    <StorageMeter class="meter" />

    <p v-if="busy" class="status muted">Reading your file… this can take a few seconds.</p>
    <p v-if="error" class="status error">{{ error }}</p>

    <div v-if="result" class="ready">
      <span class="tick"><Icon name="check" /></span>
      <div class="ready-text">
        <strong>{{ result.file.name }} is ready</strong>
        <div class="muted small">
          {{ result.sheets.length }} {{ result.sheets.length === 1 ? 'sheet' : 'sheets' }} found ·
          {{ result.sheets.map((s) => s.name).join(', ') }}
        </div>
      </div>
      <button class="btn btn-primary" @click="$emit('continue', result)">{{ continueLabel }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Icon from './Icon.vue'
import StorageMeter from './StorageMeter.vue'
import { api } from '../lib/api'
import { loadFiles, store, validateLocalFile } from '../lib/files'

defineProps({ continueLabel: { type: String, default: 'Continue' } })
defineEmits(['continue'])

const picker = ref(null)
const url = ref('')
const over = ref(false)
const busy = ref(false)
const error = ref('')
const result = ref(null)

async function run(fn) {
  error.value = ''
  result.value = null
  busy.value = true
  try {
    result.value = await fn()
    await loadFiles()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function sendFile(file) {
  if (!store.loaded) await loadFiles()
  const problem = validateLocalFile(file)
  if (problem) {
    error.value = problem
    result.value = null
    return
  }
  const form = new FormData()
  form.append('file', file)
  await run(() => api('/files/upload', { method: 'POST', form }))
}

function onPick(e) {
  const f = e.target.files[0]
  e.target.value = ''
  if (f) sendFile(f)
}

function onDrop(e) {
  over.value = false
  const f = e.dataTransfer.files[0]
  if (f) sendFile(f)
}

async function submitLink() {
  if (!url.value) return
  await run(() => api('/files/google-sheet', { method: 'POST', body: { url: url.value } }))
  if (result.value) url.value = ''
}
</script>

<style scoped>
.grid { display: grid; grid-template-columns: 1fr; gap: 14px; align-items: stretch; }
.or { text-align: center; font-size: 14px; }
.drop, .link { padding: 28px 20px; display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; }
.drop { border-style: dashed; }
.drop.over { border-color: var(--accent); background: var(--hover); }
.drop.busy { opacity: 0.6; }
h3 { margin: 4px 0 0; font-size: 17px; }
p { margin: 0; }
.small { font-size: 13px; }
.ico { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; background: var(--hover); color: var(--gold); }
.link-row { display: flex; width: 100%; gap: 0; }
.link-row input { border-radius: 14px 0 0 14px; }
.go { width: 52px; border: 0; border-radius: 0 14px 14px 0; background: var(--btn-bg); color: var(--btn-fg); display: grid; place-items: center; cursor: pointer; }
.go:disabled { opacity: 0.5; cursor: not-allowed; }
.meter { margin-top: 18px; }
.status { margin: 14px 0 0; font-size: 14px; }
.error { color: var(--danger); }
.ready { margin-top: 16px; display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-radius: 16px; border: 1px solid var(--success); background: var(--surface); }
.tick { width: 34px; height: 34px; border-radius: 50%; background: var(--success); color: #fff; display: grid; place-items: center; flex: none; }
.tick svg { width: 18px; height: 18px; }
.ready-text { flex: 1; min-width: 0; }
@media (min-width: 760px) {
  .grid { grid-template-columns: 1fr auto 1fr; }
  .or { align-self: center; }
}
</style>
