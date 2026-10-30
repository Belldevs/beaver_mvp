import { reactive } from 'vue'
import { api } from './api'
import { auth, loadProfile } from './auth'

// Kept at module level so the conversation survives switching tabs.
// Oldest first, newest last (chat order).
export const thread = reactive([])
let nextId = 1

// Steps shown while an answer is on its way. The server doesn't report progress,
// so each step appears after a short delay; the last one waits for the real answer.
export const STAGES = [
  'Parsing your question',
  'Looking through your sheets',
  'Running the calculations',
  'Preparing your answer'
]
const STAGE_DELAYS = [1200, 2800, 4600] // ms until stages 1, 2, 3 begin

export async function ask(question) {
  const item = reactive({ id: nextId++, q: question, status: 'loading', card: null, error: '', waking: false, stage: 0 })
  thread.push(item)

  const timers = STAGE_DELAYS.map((ms, i) => setTimeout(() => (item.stage = i + 1), ms))
  timers.push(setTimeout(() => (item.waking = true), 6000)) // slow first request: server is waking up

  try {
    const res = await api('/ask', { method: 'POST', body: { question } })
    item.card = res.card
    item.status = 'done'
    if (res.counted && auth.profile) auth.profile.questions_used = res.questions_used
    else if (res.counted) loadProfile()
  } catch (e) {
    item.error = e.message
    item.status = 'error'
  } finally {
    timers.forEach(clearTimeout)
  }
}
