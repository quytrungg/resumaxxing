import { useSyncExternalStore } from 'react'

export function initTheme() {
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.classList.add('dark')
  }
}

export function toggleTheme() {
  const dark = document.documentElement.classList.toggle('dark')
  localStorage.setItem('theme', dark ? 'dark' : 'light')
  window.dispatchEvent(new Event('themechange'))
}

export function useDarkMode() {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener('themechange', cb)
      return () => window.removeEventListener('themechange', cb)
    },
    () => document.documentElement.classList.contains('dark'),
  )
}
