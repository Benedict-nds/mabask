"use client"

import { useEffect } from "react"

const KEY = "aq.inventory.rev"
const EVENT = "aq:inventory"

export function notifyInventoryChanged() {
  try {
    localStorage.setItem(KEY, String(Date.now()))
  } catch { /* ignore */ }
  window.dispatchEvent(new Event(EVENT))
}

/** Refetch inventory when a sale lands, the tab is focused, or a few seconds pass. */
export function useInventoryLive(refresh: (silent?: boolean) => void) {
  useEffect(() => {
    const run = () => refresh(true)
    const onVisible = () => {
      if (document.visibilityState === "visible") run()
    }
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) run()
    }
    document.addEventListener("visibilitychange", onVisible)
    window.addEventListener("focus", run)
    window.addEventListener("storage", onStorage)
    window.addEventListener(EVENT, run)
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") run()
    }, 8000)
    return () => {
      document.removeEventListener("visibilitychange", onVisible)
      window.removeEventListener("focus", run)
      window.removeEventListener("storage", onStorage)
      window.removeEventListener(EVENT, run)
      window.clearInterval(timer)
    }
  }, [refresh])
}
