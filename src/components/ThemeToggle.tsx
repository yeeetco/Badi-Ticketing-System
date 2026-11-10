import { useEffect, useState } from 'react'

export function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem('badi-theme')
      if (saved) return saved === 'dark'
    } catch { /* Storage can be disabled in private browser settings. */ }
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    try { localStorage.setItem('badi-theme', dark ? 'dark' : 'light') } catch { /* Theme still works in memory. */ }
  }, [dark])

  return <button className="theme-toggle" type="button" aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`} onClick={() => setDark((value) => !value)}>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{dark ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></> : <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />}</svg>
    <span>{dark ? 'Light mode' : 'Dark mode'}</span>
  </button>
}
