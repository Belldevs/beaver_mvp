import { ref } from 'vue'

const KEY = 'beaver-theme'
export const theme = ref(document.documentElement.getAttribute('data-theme') || 'dark')

export function setTheme(t) {
  theme.value = t
  document.documentElement.setAttribute('data-theme', t)
  localStorage.setItem(KEY, t) // remembered from now on
}

export function toggleTheme() {
  setTheme(theme.value === 'dark' ? 'light' : 'dark')
}
