"use client"

import { useCallback, useEffect, useState } from "react"
import { Search, Plus, SlidersHorizontal, ArrowUpDown, ChevronRight, Package, ArchiveRestore } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MedicineDrawer } from "@/features/inventory/components/MedicineDrawer"
import { QuickAddProduct } from "@/features/inventory/components/QuickAddProduct"
import { asMedicine, type Medicine } from "@/lib/api/map"
import { api, ApiError } from "@/lib/api/client"
import type { InventoryCounts, Page, Product } from "@/lib/api/types"
import { daysUntil, formatExpiry } from "@/lib/format"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { useInventoryLive } from "@/lib/inventory-sync"

const statusMeta = {
  healthy: { label: "Healthy", dot: "bg-primary", variant: "success" as const },
  low: { label: "Low stock", dot: "bg-warning", variant: "warning" as const },
  critical: { label: "Critical", dot: "bg-destructive", variant: "danger" as const },
}

type SortKey = "name" | "quantity" | "expiry"
type CatalogTab = "active" | "archived"

export default function InventoryPage() {
  const { can } = useAuth()
  const canArchive = can("inventory.archive")
  const [catalog, setCatalog] = useState<CatalogTab>("active")
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
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const pageSize = 25
  const showArchived = catalog === "archived"

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const archivedParam = showArchived ? "&archived=true" : ""
      const statusParam = showArchived ? "All" : status
      const requests: [Promise<Page<Product>>, Promise<string[]>, Promise<InventoryCounts>] = [
        api<Page<Product>>(`/products?q=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&status=${statusParam}&sort=${sort}&order=${asc ? "asc" : "desc"}&limit=${pageSize}&offset=${offset}${archivedParam}`),
        api<string[]>("/categories"),
        showArchived
          ? Promise.resolve({ total: 0, healthy: 0, low: 0, critical: 0 })
          : api<InventoryCounts>("/products/summary"),
      ]
      const [page, cats, summary] = await Promise.all(requests)
      setMedicines(page.items.map(asMedicine))
      setTotal(page.total)
      setCategories(cats)
      if (!showArchived) setCounts(summary)
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
  }, [query, category, status, sort, asc, offset, showArchived])

  useEffect(() => { setOffset(0); setChecked([]); setSelected(null) }, [query, category, status, sort, asc, catalog])
  useEffect(() => { void load() }, [load])
  useInventoryLive(load)

  const restoreProduct = async (id: string) => {
    setRestoringId(id)
    try {
      await api(`/products/${id}/restore`, { method: "POST" })
      setSelected(null)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not restore product")
    } finally {
      setRestoringId(null)
    }
  }

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
        {canArchive && (
          <div className="flex w-fit items-center rounded-lg border border-border bg-card p-0.5">
            <button type="button" onClick={() => setCatalog("active")} className={cn("rounded-md px-3.5 py-1.5 text-sm font-medium", catalog === "active" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>Active</button>
            <button type="button" onClick={() => setCatalog("archived")} className={cn("rounded-md px-3.5 py-1.5 text-sm font-medium", catalog === "archived" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>Archived</button>
          </div>
        )}

        {!showArchived && (
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
        )}

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex h-9 min-w-56 flex-1 items-center gap-2 rounded-lg border border-border bg-card px-3">
            <Search className="size-4 text-muted-foreground" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name, brand, or barcode…" className="h-full flex-1 bg-transparent text-sm outline-none" />
          </div>
          {!showArchived && (
            <>
              <Select value={category} onChange={setCategory} options={["All", ...categories]} icon={<SlidersHorizontal className="size-3.5" />} />
              <Select value={status === "All" ? "All" : statusMeta[status as keyof typeof statusMeta].label} onChange={(v) => setStatus(v === "All" ? "All" : Object.keys(statusMeta).find((k) => statusMeta[k as keyof typeof statusMeta].label === v)!)} options={["All", "Healthy", "Low stock", "Critical"]} />
              {can("inventory.create") && (
                <Button size="default" className="h-9 gap-1.5" onClick={() => setAdding(true)}>
                  <Plus className="size-4" /> Add Medicine
                </Button>
              )}
            </>
          )}
        </div>

        {error && <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

        {checked.length > 0 && !showArchived && (
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
                  {!showArchived && (
                    <th className="w-10 px-4 py-3">
                      <input type="checkbox" checked={allChecked} onChange={(e) => setChecked(e.target.checked ? rows.map((r) => r.id) : [])} className="size-4 rounded border-border accent-primary" />
                    </th>
                  )}
                  <th className="px-4 py-3"><button type="button" onClick={() => { setSort("name"); setAsc((a) => sort === "name" ? !a : true) }} className="flex items-center gap-1 font-medium hover:text-foreground">Medicine <ArrowUpDown className="size-3" /></button></th>
                  <th className="px-4 py-3 font-medium">SKU</th>
                  <th className="px-4 py-3 font-medium">Category</th>
                  {showArchived ? (
                    <>
                      <th className="px-4 py-3 font-medium">Archived</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="w-28 px-4 py-3 font-medium">Action</th>
                    </>
                  ) : (
                    <>
                      <th className="px-4 py-3 font-medium">Batch</th>
                      <th className="px-4 py-3"><button type="button" onClick={() => { setSort("expiry"); setAsc((a) => sort === "expiry" ? !a : true) }} className="flex items-center gap-1 font-medium hover:text-foreground">Expiry <ArrowUpDown className="size-3" /></button></th>
                      <th className="px-4 py-3 text-right"><button type="button" onClick={() => { setSort("quantity"); setAsc((a) => sort === "quantity" ? !a : true) }} className="flex items-center gap-1 font-medium hover:text-foreground">Qty <ArrowUpDown className="size-3" /></button></th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="w-10 px-4 py-3" />
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => {
                  const meta = statusMeta[m.status]
                  const days = m.expiry ? daysUntil(m.expiry) ?? 999 : 999
                  const archivedAt = m.raw.deleted_at
                  return (
                    <tr key={m.id} onClick={() => setSelected(m)} className="cursor-pointer border-b border-border last:border-0 transition-colors hover:bg-muted/40">
                      {!showArchived && (
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <input type="checkbox" checked={checked.includes(m.id)} onChange={(e) => setChecked((c) => e.target.checked ? [...c, m.id] : c.filter((x) => x !== m.id))} className="size-4 rounded border-border accent-primary" />
                        </td>
                      )}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"><Package className="size-4" /></span>
                          <div className="leading-tight">
                            <p className="font-medium">{m.name}</p>
                            <p className="text-xs text-muted-foreground">{m.raw.generic_name || m.barcode}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{m.raw.sku || "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground">{m.category}</td>
                      {showArchived ? (
                        <>
                          <td className="px-4 py-3 text-muted-foreground">
                            {archivedAt ? new Date(archivedAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—"}
                          </td>
                          <td className="px-4 py-3"><Badge variant="neutral">Archived</Badge></td>
                          <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                            {can("inventory.restore") && (
                              <Button size="sm" variant="outline" className="gap-1" disabled={restoringId === m.id} onClick={() => void restoreProduct(m.id)}>
                                <ArchiveRestore className="size-3.5" /> {restoringId === m.id ? "…" : "Restore"}
                              </Button>
                            )}
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{m.batch || "—"}</td>
                          <td className="px-4 py-3">
                            <span className={cn(days < 60 ? "text-destructive font-medium" : "text-muted-foreground")}>
                              {m.expiry ? formatExpiry(m.expiry, { month: "short", year: "numeric" }) : "—"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-medium tabular-nums">{m.quantity.toLocaleString()}</td>
                          <td className="px-4 py-3"><Badge variant={meta.variant}><span className={cn("size-1.5 rounded-full", meta.dot)} />{meta.label}</Badge></td>
                          <td className="px-4 py-3 text-muted-foreground"><ChevronRight className="size-4" /></td>
                        </>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {!loading && rows.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
              <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground"><Search className="size-5" /></span>
              <p className="text-sm font-medium">{showArchived ? "No archived medicines" : "No medicines match your filters"}</p>
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
      <MedicineDrawer
        medicine={selected}
        onClose={() => setSelected(null)}
        onChanged={() => void load()}
        alternatives={showArchived ? [] : medicines}
        catalogMode={showArchived ? "archived" : "active"}
      />
      {adding && <QuickAddProduct onClose={() => setAdding(false)} onSaved={() => { setAdding(false); void load() }} />}
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
