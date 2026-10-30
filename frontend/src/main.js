import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initAuth } from './lib/auth'
import { configError } from './lib/supabase'
import './style.css'

// Show any startup problem on screen instead of a blank white page.
function showFatal(msg) {
  const el = document.getElementById('app')
  if (!el) return
  el.innerHTML =
    '<div style="max-width:560px;margin:15vh auto;padding:24px;font-family:system-ui,sans-serif;' +
    'border:1px solid #e4b4b4;border-radius:16px;background:#fff5f5;color:#400">' +
    '<h2 style="margin:0 0 8px">Beaver couldn\u2019t start</h2>' +
    '<p style="margin:0;line-height:1.5"></p></div>'
  el.querySelector('p').textContent = msg
}

window.addEventListener('error', (e) => {
  if (!document.querySelector('#app > *')) showFatal(e.message || 'Unknown error (see browser console).')
})
window.addEventListener('unhandledrejection', (e) => {
  if (!document.querySelector('#app > *')) showFatal(String(e.reason?.message || e.reason))
})

function start() {
  const app = createApp(App)
  app.config.errorHandler = (err) => {
    console.error(err)
    if (!document.querySelector('#app > *')) showFatal(String(err?.message || err))
  }
  app.use(router).mount('#app')
}

if (configError) {
  showFatal(configError)
} else {
  // Never wait forever for the session: if Supabase is unreachable, start anyway after 5s.
  const timeout = new Promise((resolve) => setTimeout(resolve, 5000))
  Promise.race([initAuth(), timeout])
    .catch((e) => console.error('Auth init failed', e))
    .finally(start)
}
