"use client"

import { useCallback, useEffect, useState } from "react"
import { Search, Plus, SlidersHorizontal, ArrowUpDown, ChevronRight, Package } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { MedicineDrawer } from "@/features/inventory/components/MedicineDrawer"
import { asMedicine, type Medicine } from "@/lib/api/map"
import { api, ApiError } from "@/lib/api/client"
import type { InventoryCounts, Page, Product } from "@/lib/api/types"
import { daysUntil, formatExpiry, normalizeExpiryInput } from "@/lib/format"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { useInventoryLive } from "@/lib/inventory-sync"

const statusMeta = {
  healthy: { label: "Healthy", dot: "bg-primary", variant: "success" as const },
  low: { label: "Low stock", dot: "bg-warning", variant: "warning" as const },
  critical: { label: "Critical", dot: "bg-destructive", variant: "danger" as const },
}

type SortKey = "name" | "quantity" | "expiry"

export default function InventoryPage() {
  const { can } = useAuth()
  const [query, setQuery] = useState("")
  const [category, setCategory] = useState("All")
  const [status, setStatus] = useState("All")
  const [sort, setSort] = useState<SortKey>("name")
  const [asc, setAsc] = useState(true)
  const [selected, setSelected] = useState<Medicine | null>(null)
  const [checked, setChecked] = useState<string[]>([])
  const [medicines, setMedicines] = useState<Medicine[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<InventoryCounts>({ total: 0, healthy: 0, low: 0, critical: 0 })
  const pageSize = 25

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [page, cats, summary] = await Promise.all([
        api<Page<Product>>(`/products?q=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&status=${status}&sort=${sort}&order=${asc ? "asc" : "desc"}&limit=${pageSize}&offset=${offset}`),
        api<string[]>("/categories"),
        api<InventoryCounts>("/products/summary"),
      ])
      setMedicines(page.items.map(asMedicine))
      setTotal(page.total)
      setCategories(cats)
      setCounts(summary)
      setSelected((current) => {
        if (!current) return current
        const next = page.items.find((p) => p.id === current.id)
        return next ? asMedicine(next) : current
      })
      setError(null)
    } catch (err) {
      if (!silent) setError(err instanceof ApiError ? err.message : "Failed to load inventory")
    } finally {
      if (!silent) setLoading(false)
    }
  }, [query, category, status, sort, asc, offset])

  useEffect(() => { setOffset(0) }, [query, category, status, sort, asc])
  useEffect(() => { void load() }, [load])
  useInventoryLive(load)

  const rows = medicines
  const allChecked = rows.length > 0 && checked.length === rows.length
  const summary = {
    total: counts.total || total,
    healthy: counts.healthy,
    low: counts.low,
    critical: counts.critical,
  }

  return (
    <>
      <AppTopbar title="Inventory" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-3">
          {[
            { label: "Total SKUs", value: summary.total, tone: "neutral" },
            { label: "Healthy", value: summary.healthy, tone: "success" },
            { label: "Low stock", value: summary.low, tone: "warning" },
            { label: "Critical", value: summary.critical, tone: "danger" },
          ].map((s) => (
            <div key={s.label} className="flex-1 rounded-xl border border-border bg-card px-4 py-3">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className={cn("mt-0.5 text-xl font-semibold", s.tone === "success" && "text-primary", s.tone === "warning" && "text-warning-foreground", s.tone === "danger" && "text-destructive")}>{s.value}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex h-9 min-w-56 flex-1 items-center gap-2 rounded-lg border border-border bg-card px-3">
            <Search className="size-4 text-muted-foreground" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name, brand, or barcode…" className="h-full flex-1 bg-transparent text-sm outline-none" />
          </div>
          <Select value={category} onChange={setCategory} options={["All", ...categories]} icon={<SlidersHorizontal className="size-3.5" />} />
          <Select value={status === "All" ? "All" : statusMeta[status as keyof typeof statusMeta].label} onChange={(v) => setStatus(v === "All" ? "All" : Object.keys(statusMeta).find((k) => statusMeta[k as keyof typeof statusMeta].label === v)!)} options={["All", "Healthy", "Low stock", "Critical"]} />
          {can("inventory.create") && (
            <Button size="default" className="h-9 gap-1.5" onClick={() => setAdding(true)}>
              <Plus className="size-4" /> Add Medicine
            </Button>
          )}
        </div>

        {error && <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

        {checked.length > 0 && (
          <div className="flex items-center gap-3 rounded-xl border border-secondary/30 bg-secondary/5 px-4 py-2.5 text-sm animate-fade-up">
            <span className="font-medium text-secondary">{checked.length} selected</span>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setChecked([])}>Clear</Button>
          </div>
        )}

        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                  <th className="w-10 px-4 py-3">
                    <input type="checkbox" checked={allChecked} onChange={(e) => setChecked(e.target.checked ? rows.map((r) => r.id) : [])} className="size-4 rounded border-border accent-primary" />
                  </th>
                  <th className="px-4 py-3"><button onClick={() => { setSort("name"); setAsc((a) => sort === "name" ? !a : true) }} className="flex items-center gap-1 font-medium hover:text-foreground">Medicine <ArrowUpDown className="size-3" /></button></th>
                  <th className="px-4 py-3 font-medium">Category</th>
                  <th className="px-4 py-3 font-medium">Batch</th>
                  <th className="px-4 py-3"><button onClick={() => { setSort("expiry"); setAsc((a) => sort === "expiry" ? !a : true) }} className="flex items-center gap-1 font-medium hover:text-foreground">Expiry <ArrowUpDown className="size-3" /></button></th>
                  <th className="px-4 py-3 text-right"><button onClick={() => { setSort("quantity"); setAsc((a) => sort === "quantity" ? !a : true) }} className="flex items-center gap-1 font-medium hover:text-foreground">Qty <ArrowUpDown className="size-3" /></button></th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="w-10 px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => {
                  const meta = statusMeta[m.status]
                  const days = m.expiry ? daysUntil(m.expiry) ?? 999 : 999
                  return (
                    <tr key={m.id} onClick={() => setSelected(m)} className="cursor-pointer border-b border-border last:border-0 transition-colors hover:bg-muted/40">
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={checked.includes(m.id)} onChange={(e) => setChecked((c) => e.target.checked ? [...c, m.id] : c.filter((x) => x !== m.id))} className="size-4 rounded border-border accent-primary" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"><Package className="size-4" /></span>
                          <div className="leading-tight">
                            <p className="font-medium">{m.name}</p>
                            <p className="font-mono text-xs text-muted-foreground">{m.barcode}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{m.category}</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{m.batch || "—"}</td>
                      <td className="px-4 py-3">
                        <span className={cn(days < 60 ? "text-destructive font-medium" : "text-muted-foreground")}>
                          {m.expiry ? formatExpiry(m.expiry, { month: "short", year: "numeric" }) : "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-medium tabular-nums">{m.quantity.toLocaleString()}</td>
                      <td className="px-4 py-3"><Badge variant={meta.variant}><span className={cn("size-1.5 rounded-full", meta.dot)} />{meta.label}</Badge></td>
                      <td className="px-4 py-3 text-muted-foreground"><ChevronRight className="size-4" /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {!loading && rows.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
              <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground"><Search className="size-5" /></span>
              <p className="text-sm font-medium">No medicines match your filters</p>
            </div>
          )}
          <div className="flex items-center justify-between border-t border-border px-4 py-3 text-xs text-muted-foreground">
            <span>{loading ? "Loading…" : `Showing ${rows.length ? offset + 1 : 0}–${offset + rows.length} of ${total}`}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - pageSize))}>Previous</Button>
              <Button variant="outline" size="sm" disabled={offset + pageSize >= total} onClick={() => setOffset((o) => o + pageSize)}>Next</Button>
            </div>
          </div>
        </div>
      </div>
      <MedicineDrawer medicine={selected} onClose={() => setSelected(null)} onChanged={() => void load()} alternatives={medicines} />
      {adding && <AddMedicine onClose={() => setAdding(false)} onSaved={() => { setAdding(false); void load() }} />}
    </>
  )
}

function Select({ value, onChange, options, icon }: { value: string; onChange: (v: string) => void; options: string[]; icon?: React.ReactNode }) {
  return (
    <div className="relative flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card pl-3 pr-2 text-sm">
      {icon}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="h-full bg-transparent pr-1 text-sm outline-none">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function AddMedicine({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setSaving(true)
    try {
      await api("/products", {
        method: "POST",
        body: JSON.stringify({
          sku: fd.get("sku"),
          barcode: fd.get("barcode"),
          name: fd.get("name"),
          brand: fd.get("brand"),
          category: fd.get("category"),
          selling_price: fd.get("price"),
          cost_price: fd.get("cost") || "0",
          reorder_threshold: Number(fd.get("reorder") || 0),
          initial_quantity: Number(fd.get("qty") || 0),
          batch_number: fd.get("batch") || "",
          expiry_date: fd.get("expiry") ? normalizeExpiryInput(String(fd.get("expiry"))) : null,
        }),
      })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save")
    } finally {
      setSaving(false)
    }
  }
  return (
    <Overlay onClose={onClose}>
      <form onSubmit={submit} onClick={(e) => e.stopPropagation()} className="w-full max-w-lg space-y-3 rounded-2xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold">Add medicine</h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            ["name", "Name", "Amoxicillin 500mg"],
            ["brand", "Brand", "Amoxil"],
            ["sku", "SKU", "MD-2001"],
            ["barcode", "Barcode", "8901234500999"],
            ["category", "Category", "Antibiotics"],
            ["price", "Selling price", "0.35"],
            ["cost", "Cost", "0.18"],
            ["reorder", "Reorder point", "100"],
            ["qty", "Opening qty", "0"],
            ["batch", "Batch", ""],
          ].map(([name, label, ph]) => (
            <label key={name} className="flex flex-col gap-1 text-sm">
              {label}
              <input name={name} placeholder={ph} className="h-9 rounded-lg border border-border px-3 text-sm outline-none" required={["name", "sku", "barcode", "category", "price"].includes(name)} />
            </label>
          ))}
          <label className="flex flex-col gap-1 text-sm">
            Expiry
            <input name="expiry" type="date" min="2000-01-01" max="2099-12-31" className="h-9 rounded-lg border border-border px-3 text-sm outline-none" />
          </label>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
        </div>
      </form>
    </Overlay>
  )
}
