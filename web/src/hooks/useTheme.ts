import { useCallback, useEffect, useState } from 'react'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'aiw-theme'

/**
 * Read the theme the user settled on last time, falling back to dark.
 *
 * Dark is the default rather than the OS preference because the platform is designed dark-first
 * and light is the deliberate alternative — opening in a theme the product was not designed
 * around is a worse first impression than ignoring the OS hint.
 */
export function storedTheme(): Theme {
  if (typeof localStorage === 'undefined') return 'dark'
  return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
}

/** Apply a theme to <html>. Exported so it can run before React mounts, avoiding a light flash. */
export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.style.colorScheme = theme
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(storedTheme)

  useEffect(() => {
    applyTheme(theme)
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
  }, [])

  return { theme, setTheme, toggle }
}
