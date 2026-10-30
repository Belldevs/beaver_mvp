<template>
  <section class="page">
    <h1 class="h1">Admin</h1>
    <p v-if="error" class="error">{{ error }}</p>
    <template v-if="data">
      <div class="stats">
        <div class="card stat"><span class="muted small">Questions today</span><strong>{{ data.questions_today }} of {{ data.global_daily_cap }}</strong></div>
        <div class="card stat"><span class="muted small">Storage left (approx.)</span><strong>{{ formatBytes(Math.max(0, data.storage_limit_bytes - data.storage_used_bytes)) }}</strong></div>
        <div class="card stat"><span class="muted small">Users</span><strong>{{ data.users.length }}</strong></div>
      </div>
      <div class="card table-wrap">
        <table>
          <thead><tr><th>Email</th><th>Questions</th><th>Storage</th><th>Last active</th><th></th></tr></thead>
          <tbody>
            <tr v-for="u in data.users" :key="u.id">
              <td>{{ u.email }}<span v-if="u.is_admin" class="muted"> (admin)</span></td>
              <td>{{ u.questions_used }}</td>
              <td>{{ formatBytes(u.storage_bytes) }}</td>
              <td>{{ timeAgo(u.last_active_at) }}</td>
              <td><button class="btn btn-outline sm" :disabled="u.id === auth.user.id" @click="toggle(u)">{{ u.suspended ? 'Unsuspend' : 'Suspend' }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { auth } from '../lib/auth'
import { formatBytes, timeAgo } from '../lib/files'

const data = ref(null)
const error = ref('')
const load = () => api('/admin/overview').then((d) => (data.value = d)).catch((e) => (error.value = e.message))
onMounted(load)
async function toggle(u) {
  try { await api(`/admin/users/${u.id}/suspend`, { method: 'POST', body: { suspended: !u.suspended } }); u.suspended = !u.suspended } catch (e) { error.value = e.message }
}
</script>

<style scoped>
.page { padding-top: 12px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }
.stat { padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }
.small { font-size: 13px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--muted); font-weight: 500; }
.sm { padding: 6px 12px; font-size: 13px; }
.error { color: var(--danger); }
</style>
