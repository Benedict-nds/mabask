"use client"

import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { Plus, Search, X } from "lucide-react"
import { api } from "@/lib/api/client"
import type { Page, Product } from "@/lib/api/types"
import { currency } from "@/lib/format"

type Props = {
  /** Currently selected product label (null when nothing chosen). */
  value: { id: string; name: string; sku?: string } | null
  onSelect: (product: Product) => void
  /** Offers "Create new medicine" with whatever the user typed. */
  onCreateNew?: (typedName: string) => void
  onClear?: () => void
  placeholder?: string
  autoFocus?: boolean
  className?: string
  showStock?: boolean
}

/** Server-backed medicine typeahead. Archived products are never offered (the API excludes them). */
export function ProductPicker({
  value,
  onSelect,
  onCreateNew,
  onClear,
  placeholder = "Search medicine by name, SKU or barcode…",
  autoFocus = false,
  className = "",
  showStock = true,
}: Props) {
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const term = query.trim()
    let cancelled = false
    setLoading(true)
    const timer = window.setTimeout(() => {
      api<Page<Product>>(`/products?q=${encodeURIComponent(term)}&limit=10&sort=name&order=asc`)
        .then((page) => {
          if (cancelled) return
          setResults(page.items)
          setHighlight(0)
        })
        .catch(() => !cancelled && setResults([]))
        .finally(() => !cancelled && setLoading(false))
    }, 180)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query, open])

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const el = inputRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      setRect({ top: r.bottom + 4, left: r.left, width: Math.max(r.width, 320) })
    }
    place()
    window.addEventListener("scroll", place, true)
    window.addEventListener("resize", place)
    return () => {
      window.removeEventListener("scroll", place, true)
      window.removeEventListener("resize", place)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (wrapRef.current?.contains(target) || listRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener("mousedown", onDown)
    return () => document.removeEventListener("mousedown", onDown)
  }, [open])

  const choose = (product: Product) => {
    onSelect(product)
    setQuery("")
    setOpen(false)
  }

  const createNew = () => {
    onCreateNew?.(query.trim())
    setOpen(false)
  }

  const optionCount = results.length + (onCreateNew ? 1 : 0)

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter")) {
      setOpen(true)
      return
    }
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setHighlight((h) => Math.min(h + 1, Math.max(optionCount - 1, 0)))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      if (highlight < results.length) choose(results[highlight])
      else if (onCreateNew) createNew()
    } else if (e.key === "Escape") {
      e.stopPropagation()
      setOpen(false)
    }
  }

  const display = open ? query : value ? value.name : query

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={inputRef}
        value={display}
        autoFocus={autoFocus}
        placeholder={value ? value.name : placeholder}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onKeyDown={onKeyDown}
        className="h-9 w-full rounded-lg border border-border bg-background pl-8 pr-7 text-sm outline-none focus:border-primary"
        aria-label="Search medicine"
        role="combobox"
        aria-expanded={open}
      />
      {value && onClear && !open && (
        <button
          type="button"
          onClick={onClear}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          aria-label="Clear medicine"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      {open && rect && (
        <div
          ref={listRef}
          role="listbox"
          style={{ position: "fixed", top: rect.top, left: rect.left, width: rect.width, zIndex: 80 }}
          className="max-h-72 overflow-y-auto rounded-xl border border-border bg-card p-1 shadow-xl"
        >
          {loading && results.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
          {!loading && results.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              {query.trim() ? `No medicine matches “${query.trim()}”.` : "No medicines found."}
            </p>
          )}
          {results.map((p, i) => (
            <button
              key={p.id}
              type="button"
              role="option"
              aria-selected={i === highlight}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => choose(p)}
              className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm ${
                i === highlight ? "bg-muted" : ""
              }`}
            >
              <span className="min-w-0">
                <span className="block truncate font-medium">{p.name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {p.sku}
                  {p.strength ? ` · ${p.strength}` : ""}
                  {!p.is_active ? " · inactive" : ""}
                </span>
              </span>
              <span className="shrink-0 text-right text-xs text-muted-foreground">
                <span className="block">{currency(p.selling_price)}</span>
                {showStock && <span className="block">{p.quantity_on_hand} in stock</span>}
              </span>
            </button>
          ))}
          {onCreateNew && (
            <button
              type="button"
              onMouseEnter={() => setHighlight(results.length)}
              onClick={createNew}
              className={`mt-1 flex w-full items-center gap-2 rounded-lg border-t border-border px-3 py-2 text-left text-sm font-medium text-primary ${
                highlight === results.length ? "bg-muted" : ""
              }`}
            >
              <Plus className="h-4 w-4" />
              {query.trim() ? `Create new medicine “${query.trim()}”` : "Create new medicine"}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
