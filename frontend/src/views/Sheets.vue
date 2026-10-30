<template>
  <section class="page">
    <h1 class="h1">Sheets</h1>
    <p class="muted sub">Add a file or link, or remove one to free up space.</p>

    <UploadPanel continue-label="Ask a question" @continue="router.push('/')" />

    <h2 class="h2 list-title">Your files</h2>
    <div v-if="!store.files.length" class="card empty muted">No files yet.</div>

    <div v-for="f in store.files" :key="f.id" class="card file">
      <div class="file-head">
        <div class="file-info">
          <strong class="name">{{ f.name }}</strong>
          <span class="muted small">
            {{ formatBytes(f.size_bytes) }} · {{ f.source === 'google_sheet' ? 'Google Sheet' : 'Uploaded' }} ·
            {{ timeAgo(f.created_at) }}
          </span>
        </div>
        <button class="icon-btn" :disabled="deleting === f.id" :aria-label="`Delete ${f.name}`" @click="remove(f)">
          <Icon name="trash" />
        </button>
      </div>
      <div class="chips">
        <span v-for="s in f.sheets" :key="s.id" class="chip">{{ s.name }} · {{ s.row_count.toLocaleString() }} rows</span>
      </div>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import UploadPanel from '../components/UploadPanel.vue'
import { api } from '../lib/api'
import { formatBytes, loadFiles, store, timeAgo } from '../lib/files'

const router = useRouter()
const deleting = ref('')
const error = ref('')

onMounted(loadFiles)

async function remove(f) {
  if (!confirm(`Delete “${f.name}” and all its sheets? This can't be undone.`)) return
  error.value = ''
  deleting.value = f.id
  try {
    await api(`/files/${f.id}`, { method: 'DELETE' })
    await loadFiles()
  } catch (e) {
    error.value = e.message
  } finally {
    deleting.value = ''
  }
}
</script>

<style scoped>
.page { padding-top: 12px; }
.sub { margin: 0 0 22px; }
.list-title { margin: 32px 0 12px; }
.empty { padding: 24px; text-align: center; }
.file { padding: 16px 18px; margin-bottom: 12px; }
.file-head { display: flex; align-items: center; gap: 12px; }
.file-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.small { font-size: 13px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.chip { font-size: 13px; padding: 6px 12px; border-radius: 99px; background: var(--hover); border: 1px solid var(--border); }
.error { color: var(--danger); }
</style>
