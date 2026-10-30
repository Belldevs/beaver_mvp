import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './lib/auth'
import AppShell from './components/AppShell.vue'
import AuthView from './views/AuthView.vue'
import Home from './views/Home.vue'
import History from './views/History.vue'
import Account from './views/Account.vue'
import Admin from './views/Admin.vue'
import Sheets from './views/Sheets.vue'
import Onboarding from './views/Onboarding.vue'

const routes = [
  { path: '/signup', component: AuthView, meta: { guest: true, mode: 'signup' } },
  { path: '/login', component: AuthView, meta: { guest: true, mode: 'login' } },
  { path: '/onboarding', component: Onboarding, meta: { auth: true } },
  {
    path: '/',
    component: AppShell,
    meta: { auth: true },
    children: [
      { path: '', name: 'ask', component: Home },
      { path: 'sheets', name: 'sheets', component: Sheets },
      { path: 'history', name: 'history', component: History },
      { path: 'account', name: 'account', component: Account },
      { path: 'admin', name: 'admin', component: Admin, meta: { admin: true } }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (to.meta.auth && !auth.user) return '/signup'
  if (to.meta.guest && auth.user) return '/'
  if (to.meta.admin && !auth.profile?.is_admin) return '/'
})

// When a login completes (e.g. Google redirect), move into the app.
import { watch } from 'vue'
watch(
  () => auth.user,
  (u) => {
    const r = router.currentRoute.value
    if (u && r.meta.guest) router.replace('/')
    if (!u && r.meta.auth) router.replace('/login')
  }
)

export default router
