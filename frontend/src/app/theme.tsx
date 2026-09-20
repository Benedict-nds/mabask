"use client"

import { createContext, useContext, useEffect, useMemo, useState } from "react"

export type Theme = "light" | "dark" | "system"

const STORAGE_KEY = "aq.theme"

type ThemeState = {
  theme: Theme
  resolved: "light" | "dark"
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeState | null>(null)

function systemDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && systemDark())
  document.documentElement.classList.toggle("dark", dark)
  document.documentElement.classList.toggle("light", !dark)
  document.documentElement.style.colorScheme = dark ? "dark" : "light"
  document.cookie = `aq.color-scheme=${dark ? "dark" : "light"}; Path=/; Max-Age=31536000; SameSite=Lax`
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system")

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === "light" || stored === "dark" || stored === "system") {
      setThemeState(stored)
      applyTheme(stored)
    } else {
      applyTheme("system")
    }
  }, [])

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      if ((localStorage.getItem(STORAGE_KEY) || "system") === "system") applyTheme("system")
    }
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [])

  const value = useMemo<ThemeState>(() => {
    const resolved = theme === "dark" || (theme === "system" && typeof window !== "undefined" && systemDark()) ? "dark" : "light"
    return {
      theme,
      resolved: theme === "system" ? (typeof document !== "undefined" && document.documentElement.classList.contains("dark") ? "dark" : "light") : resolved,
      setTheme: (next) => {
        localStorage.setItem(STORAGE_KEY, next)
        setThemeState(next)
        applyTheme(next)
      },
    }
  }, [theme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider")
  return ctx
}
