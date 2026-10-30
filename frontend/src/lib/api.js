import { supabase } from './supabase'

const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

// Calls the Beaver backend with the logged-in user's token. Throws Error(message) in plain English.
export async function api(path, { method = 'GET', body, form } = {}) {
  const { data } = await supabase.auth.getSession()
  const headers = { Authorization: `Bearer ${data.session?.access_token}` }
  if (body) headers['Content-Type'] = 'application/json'

  let res
  try {
    res = await fetch(BASE + path, { method, headers, body: form ?? (body ? JSON.stringify(body) : undefined) })
  } catch {
    throw new Error("Can't reach Beaver's server. Check your connection, and that the backend is running.")
  }
  const payload = await res.json().catch(() => null)
  if (!res.ok) {
    const d = payload?.detail
    throw new Error(typeof d === 'string' ? d : `Something went wrong (${res.status}). Please try again.`)
  }
  return payload
}
