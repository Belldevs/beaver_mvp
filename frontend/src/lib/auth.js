import { reactive } from 'vue'
import { supabase } from './supabase'

export const auth = reactive({ ready: false, user: null, profile: null })

export async function loadProfile() {
  if (!auth.user) return
  const { data } = await supabase
    .from('profiles')
    .select('id,email,is_admin,questions_used,currency')
    .eq('id', auth.user.id)
    .maybeSingle()
  auth.profile = data
}

export async function initAuth() {
  const { data } = await supabase.auth.getSession()
  auth.user = data.session?.user ?? null
  if (auth.user) await loadProfile()
  auth.ready = true

  supabase.auth.onAuthStateChange((_event, session) => {
    auth.user = session?.user ?? null
    if (!auth.user) auth.profile = null
    // Defer to avoid calling Supabase from inside its own auth callback.
    else setTimeout(loadProfile, 0)
  })
}

export const signInWithGoogle = () =>
  supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin }
  })

export const signUpWithEmail = (email, password) =>
  supabase.auth.signUp({ email, password, options: { emailRedirectTo: window.location.origin } })

export const signInWithEmail = (email, password) =>
  supabase.auth.signInWithPassword({ email, password })

export const signOut = () => supabase.auth.signOut()
