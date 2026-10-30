import { computed, reactive } from 'vue'
import { supabase } from './supabase'

export const LIMIT_BYTES = 10 * 1024 * 1024 // 10 MB total per user (the backend enforces this too)

export const store = reactive({ files: [], loaded: false })

export async function loadFiles() {
  const { data, error } = await supabase
    .from('files')
    .select('id,name,source,size_bytes,created_at,sheets(id,name,row_count,created_at)')
    .order('created_at', { ascending: false })
  if (!error) {
    store.files = data
    store.loaded = true
  }
}

export const usedBytes = computed(() => store.files.reduce((sum, f) => sum + Number(f.size_bytes || 0), 0))
export const allSheets = computed(() =>
  store.files.flatMap((f) => (f.sheets || []).map((s) => ({ ...s, fileName: f.name })))
)

export function formatBytes(b) {
  if (b < 1024 * 1024) return `${Math.max(0, Math.round(b / 1024))} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

export function timeAgo(iso) {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const h = Math.floor(mins / 60)
  if (h < 24) return `${h} hr ago`
  return `${Math.floor(h / 24)} d ago`
}

// Quick checks in the browser. The backend repeats them, so this is only for fast, friendly feedback.
export function validateLocalFile(file) {
  const name = file.name.toLowerCase()
  if (!name.endsWith('.xlsx') && !name.endsWith('.csv')) return 'Only .xlsx and .csv files are supported.'
  if (file.size === 0) return 'That file is empty.'
  if (file.size > LIMIT_BYTES) return `This file is ${formatBytes(file.size)}. Beaver's limit is 10 MB in total.`
  const remaining = Math.max(0, LIMIT_BYTES - usedBytes.value)
  if (file.size > remaining) {
    return `This file is ${formatBytes(file.size)} but you only have ${formatBytes(remaining)} left of your 10 MB. Delete a file on the Sheets tab to free up space.`
  }
  return ''
}
