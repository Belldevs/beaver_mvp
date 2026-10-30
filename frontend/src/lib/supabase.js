import { createClient } from '@supabase/supabase-js'

const url = (import.meta.env.VITE_SUPABASE_URL || '').trim()
const anonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY || '').trim()

// Never throw at import time: a throw here kills the whole app and leaves a blank white page.
// Instead, remember the problem so main.js can show it on screen.
export const configError =
  !url || !anonKey
    ? 'Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. Put them in frontend/.env (same folder as package.json), then stop and restart "npm run dev".'
    : !/^https?:\/\//.test(url)
      ? 'VITE_SUPABASE_URL must start with https:// (copy the Project URL from Supabase -> Project Settings -> API).'
      : ''

export const supabase = createClient(configError ? 'http://localhost:54321' : url, configError ? 'missing-key' : anonKey)
