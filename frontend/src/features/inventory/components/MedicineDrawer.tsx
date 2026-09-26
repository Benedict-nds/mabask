"use client"

import { useCallback, useEffect, useState } from "react"
import {
  X,
  Package,
  Building2,
  TrendingUp,
  Pencil,
  ShoppingCart,
  CalendarClock,
  Archive,
  ArchiveRestore,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { currency, daysLeftLabel, daysUntil, formatExpiry, normalizeExpiryInput } from "@/lib/format"
import { type Medicine } from "@/lib/api/map"
import { api, ApiError } from "@/lib/api/client"
import type { Page, Product } from "@/lib/api/types"
import { useRouter } from "next/navigation"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { useInventoryLive } from "@/lib/inventory-sync"

const statusMeta = {
  healthy: { label: "Healthy", variant: "success" as const },
  low: { label: "Low stock", variant: "warning" as const },
  critical: { label: "Critical", variant: "danger" as const },
}

type Movement = {
  id: string
  quantity: number
  previous_quantity: number
  resulting_quantity: number
  movement_type: string
  reason: string
  created_at: string
  reference_type?: string
  reference_id?: string
  po_number?: string | null
  supplier_id?: string | null
  supplier_name?: string | null
}

export function MedicineDrawer({
  medicine,
  onClose,
  onChanged,
  alternatives = [],
  catalogMode = "active",
}: {
  medicine: Medicine | null
  onClose: () => void
  onChanged?: () => void
  alternatives?: Medicine[]
  catalogMode?: "active" | "archived"
}) {
  const router = useRouter()
  const { can } = useAuth()
  const [product, setProduct] = useState<Product | null>(medicine?.raw ?? null)
  const [movements, setMovements] = useState<Movement[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const isArchived = catalogMode === "archived" || Boolean(product?.deleted_at ?? medicine?.raw.deleted_at)

  useEffect(() => {
    if (!medicine) {
      setProduct(null)
      setMovements([])
      return
    }
    setEditing(false)
    setProduct(medicine.raw)
    api<Product>(`/products/${medicine.id}`)
      .then(setProduct)
      .catch(() => setProduct(medicine.raw))
    api<Page<Movement>>(`/stock-movements?product_id=${medicine.id}&limit=8`)
      .then((page) => setMovements(page.items))
      .catch(() => setMovements([]))
  }, [medicine])

  const refreshLive = useCallback((silent?: boolean) => {
    if (!medicine) return
    api<Product>(`/products/${medicine.id}`)
      .then((next) => {
        setProduct(next)
        if (!silent) onChanged?.()
      })
      .catch(() => undefined)
    api<Page<Movement>>(`/stock-movements?product_id=${medicine.id}&limit=8`)
      .then((page) => setMovements(page.items))
      .catch(() => undefined)
  }, [medicine, onChanged])
  useInventoryLive(refreshLive)

  if (!medicine || !product) return null
  const m = medicine
  const meta = statusMeta[product.status]
  const batches = product.batches ?? []
  const nearest = batches.slice().sort((a, b) => a.expiry_date.localeCompare(b.expiry_date))[0]
  const days = nearest ? daysUntil(nearest.expiry_date) ?? 0 : 0
  const alts = alternatives.filter((x) => x.category === m.category && x.id !== m.id).slice(0, 3)
  const margin = Number(product.selling_price)
    ? Math.round(((Number(product.selling_price) - Number(product.cost_price)) / Number(product.selling_price)) * 100)
    : 0

  const refresh = async () => {
    const next = await api<Product>(`/products/${product.id}`)
    setProduct(next)
    const page = await api<Page<Movement>>(`/stock-movements?product_id=${product.id}&limit=8`)
    setMovements(page.items)
    onChanged?.()
  }

  const addBatch = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      await api(`/products/${product.id}/batches`, {
        method: "POST",
        body: JSON.stringify({
          batch_number: fd.get("batch_number"),
          expiry_date: normalizeExpiryInput(String(fd.get("expiry_date") || "")),
          quantity: Number(fd.get("quantity") || 0),
          cost_price: fd.get("cost_price") || undefined,
        }),
      })
      e.currentTarget.reset()
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add batch")
    } finally {
      setBusy(false)
    }
  }

  const adjust = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      await api(`/products/${product.id}/adjust`, {
        method: "POST",
        body: JSON.stringify({
          quantity_delta: Number(fd.get("quantity_delta")),
          reason: fd.get("reason"),
          movement_type: fd.get("movement_type") || "ADJUSTMENT",
          batch_id: fd.get("batch_id") || null,
        }),
      })
      e.currentTarget.reset()
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Adjustment failed")
    } finally {
      setBusy(false)
    }
  }

  const archiveProduct = async () => {
    if (!window.confirm(`Archive ${product.name}? It will leave the active catalog but keep all history.`)) return
    setBusy(true)
    setError(null)
    try {
      await api(`/products/${product.id}/archive`, { method: "POST" })
      onChanged?.()
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not archive product")
    } finally {
      setBusy(false)
    }
  }

  const restoreProduct = async () => {
    setBusy(true)
    setError(null)
    try {
      await api(`/products/${product.id}/restore`, { method: "POST" })
      onChanged?.()
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not restore product")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Overlay onClose={onClose} className="items-stretch justify-end p-0 backdrop-blur-sm">
      <div className="relative flex h-full w-full max-w-md flex-col overflow-hidden border-l border-border bg-card shadow-2xl animate-fade-up" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="flex items-start gap-3 border-b border-border p-5">
          <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Package className="size-5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold leading-tight">{product.name}</h2>
              {isArchived && <Badge variant="neutral">Archived</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">{product.brand} · {product.category}</p>
            {isArchived && product.deleted_at && (
              <p className="mt-1 text-xs text-muted-foreground">
                Archived {new Date(product.deleted_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
              </p>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto scrollbar-thin p-5">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="In stock" value={Number(product.quantity_on_hand).toLocaleString()} />
            <Stat label="Reorder at" value={Number(product.reorder_threshold).toLocaleString()} />
            <div className="rounded-xl border border-border bg-background p-3">
              <p className="text-xs text-muted-foreground">Status</p>
              <Badge variant={meta.variant} className="mt-1.5">{meta.label}</Badge>
            </div>
          </div>

          {product.status !== "healthy" && (
            <div className="rounded-xl border border-warning/30 bg-warning/10 p-4">
              <p className="text-sm leading-relaxed">
                {product.name} is at {product.quantity_on_hand} units (reorder at {product.reorder_threshold}).
                Create a purchase order to replenish stock.
              </p>
              {can("purchases.create") && (
                <Button size="sm" className="mt-3 gap-1.5" onClick={() => router.push(`/suppliers?create=${product.id}`)}>
                  <ShoppingCart className="size-3.5" /> Create purchase order
                </Button>
              )}
            </div>
          )}

          <Section title="Pricing" icon={TrendingUp}>
            {editing && can("inventory.update") && !isArchived ? (
              <form
                className="grid grid-cols-2 gap-2 rounded-xl border border-border bg-background p-3"
                onSubmit={async (e) => {
                  e.preventDefault()
                  const fd = new FormData(e.currentTarget)
                  setBusy(true)
                  setError(null)
                  try {
                    const next = await api<Product>(`/products/${product.id}`, {
                      method: "PATCH",
                      body: JSON.stringify({
                        name: fd.get("name"),
                        sku: String(fd.get("sku") || "").trim() || null,
                        barcode: String(fd.get("barcode") || "").trim() || null,
                        category: String(fd.get("category") || "").trim() || "General",
                        selling_price: fd.get("selling_price"),
                        cost_price: fd.get("cost_price"),
                        reorder_threshold: Number(fd.get("reorder_threshold")),
                      }),
                    })
                    setProduct(next)
                    setEditing(false)
                    onChanged?.()
                  } catch (err) {
                    setError(err instanceof ApiError ? err.message : "Update failed")
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                <label className="col-span-2 flex flex-col gap-1 text-xs text-muted-foreground">
                  Medicine name *
                  <input name="name" required maxLength={200} defaultValue={product.name} className="h-9 rounded-lg border border-border px-3 text-sm text-foreground" />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Cost price *
                  <input name="cost_price" required type="number" min={0} step="any" defaultValue={String(product.cost_price)} className="h-9 rounded-lg border border-border px-3 text-sm text-foreground" />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Selling price *
                  <input name="selling_price" required type="number" min={0} step="any" defaultValue={String(product.selling_price)} className="h-9 rounded-lg border border-border px-3 text-sm text-foreground" />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Reorder point *
                  <input name="reorder_threshold" required type="number" min={0} step={1} defaultValue={product.reorder_threshold} className="h-9 rounded-lg border border-border px-3 text-sm text-foreground" />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Category (optional)
                  <input name="category" defaultValue={product.category} placeholder="General" className="h-9 rounded-lg border border-border px-3 text-sm text-foreground" />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  SKU (optional)
                  <input name="sku" defaultValue={product.sku} className="h-9 rounded-lg border border-border px-3 text-sm text-foreground" />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Barcode (optional)
                  <input name="barcode" defaultValue={product.barcode} className="h-9 rounded-lg border border-border px-3 text-sm text-foreground" />
                </label>
                <div className="col-span-2 flex gap-2">
                  <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => setEditing(false)}>Cancel</Button>
                  <Button type="submit" size="sm" className="flex-1" disabled={busy}>{busy ? "Saving…" : "Save product"}</Button>
                </div>
              </form>
            ) : (
              <div className="rounded-xl border border-border bg-background p-4">
                <div className="flex items-baseline justify-between">
                  <p className="text-2xl font-semibold">{currency(Number(product.selling_price))}<span className="ml-1 text-xs font-normal text-muted-foreground">/ unit</span></p>
                  <Badge variant="success">{margin}% margin</Badge>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Cost {currency(Number(product.cost_price))} · SKU {product.sku || "—"} · Barcode {product.barcode || "—"}
                </p>
              </div>
            )}
          </Section>

          <Section title="Batches" icon={CalendarClock}>
            <div className="space-y-2">
              {batches.length === 0 && <p className="text-sm text-muted-foreground">No batches on file yet.</p>}
              {batches.map((b) => {
                const left = daysUntil(b.expiry_date) ?? 0
                const supplierLabel = b.supplier?.name ?? (b.purchase_order ? "Unknown" : "Not recorded")
                const poLabel = b.purchase_order?.po_number || (b.purchase_order ? "Unknown" : null)
                return (
                  <div key={b.id} className="rounded-xl border border-border bg-background p-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-mono text-xs">{b.batch_number}</span>
                      <span className={cn("font-medium", left < 60 ? "text-destructive" : left < 180 ? "text-warning-foreground" : "text-primary")}>
                        {b.quantity} units · {daysLeftLabel(b.expiry_date)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Expires {formatExpiry(b.expiry_date, { day: "numeric", month: "long", year: "numeric" })}
                      {" · "}Cost {currency(Number(b.cost_price))}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Supplier: {supplierLabel}
                      {poLabel ? ` · PO ${poLabel}` : ""}
                      {b.received_at ? ` · Received ${new Date(b.received_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}` : ""}
                    </p>
                    {b.purchase_order && b.supplier && (
                      <p className="mt-1.5 text-[11px] text-muted-foreground/90">
                        Batch {b.batch_number} received through {poLabel} from {b.supplier.name}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </Section>

          {can("inventory.adjust") && !isArchived && (
            <>
              <Section title="Add batch" icon={Package}>
                <form onSubmit={addBatch} className="grid grid-cols-2 gap-2 rounded-xl border border-border bg-background p-3">
                  <input name="batch_number" required placeholder="Batch number" className="h-9 rounded-lg border border-border px-3 text-sm" />
                  <input name="expiry_date" required type="date" min="2000-01-01" max="2099-12-31" className="h-9 rounded-lg border border-border px-3 text-sm" />
                  <input name="quantity" type="number" min={0} defaultValue={0} placeholder="Qty" className="h-9 rounded-lg border border-border px-3 text-sm" />
                  <input name="cost_price" placeholder="Cost (optional)" className="h-9 rounded-lg border border-border px-3 text-sm" />
                  <Button type="submit" size="sm" className="col-span-2" disabled={busy}>{busy ? "Saving…" : "Add batch"}</Button>
                </form>
              </Section>
              <Section title="Stock adjustment" icon={Pencil}>
                <form onSubmit={adjust} className="grid grid-cols-2 gap-2 rounded-xl border border-border bg-background p-3">
                  <input name="quantity_delta" required type="number" placeholder="Delta (+/−)" className="h-9 rounded-lg border border-border px-3 text-sm" />
                  <select name="batch_id" className="h-9 rounded-lg border border-border px-3 text-sm">
                    <option value="">No batch (decrease only)</option>
                    {batches.map((b) => <option key={b.id} value={b.id}>{b.batch_number}</option>)}
                  </select>
                  <select name="movement_type" className="h-9 rounded-lg border border-border px-3 text-sm">
                    <option value="ADJUSTMENT">Adjustment</option>
                    <option value="DAMAGE">Damage</option>
                    <option value="EXPIRY">Expiry</option>
                  </select>
                  <input name="reason" required placeholder="Reason" className="h-9 rounded-lg border border-border px-3 text-sm" />
                  <Button type="submit" size="sm" className="col-span-2" disabled={busy}>{busy ? "Saving…" : "Apply adjustment"}</Button>
                </form>
              </Section>
            </>
          )}

          <Section title="Stock movements" icon={Building2}>
            <div className="rounded-xl border border-border bg-background">
              <div className="flex items-center justify-between border-b border-border p-4">
                <div>
                  <p className="text-sm font-medium">{product.supplier_name || "No supplier"}</p>
                  <p className="text-xs text-muted-foreground">Preferred supplier · cost {currency(Number(product.cost_price))}</p>
                </div>
              </div>
              {movements.length === 0 ? (
                <p className="px-4 py-6 text-sm text-muted-foreground">No movements recorded yet.</p>
              ) : (
                <ul className="divide-y divide-border text-sm">
                  {movements.map((mv) => (
                    <li key={mv.id} className="flex flex-col gap-0.5 px-4 py-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-muted-foreground">{new Date(mv.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
                        <span className="tabular-nums">{mv.movement_type} {mv.quantity > 0 ? "+" : ""}{mv.quantity}</span>
                        <span className="font-medium tabular-nums">{mv.previous_quantity} → {mv.resulting_quantity}</span>
                      </div>
                      {mv.reference_type === "purchase_order" && (mv.po_number || mv.supplier_name) && (
                        <p className="text-xs text-muted-foreground">
                          {mv.po_number ? `Purchase Order: ${mv.po_number}` : "Purchase Order"}
                          {mv.supplier_name ? ` · Supplier: ${mv.supplier_name}` : ""}
                        </p>
                      )}
                      {mv.reference_type === "manual_receipt" && (
                        <p className="text-xs text-muted-foreground">Manual receipt (no PO) · Supplier: Not recorded</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Section>

          <Section title="Alternative medicines" icon={Package}>
            <div className="flex flex-col gap-2">
              {alts.length === 0 && <p className="text-sm text-muted-foreground">No alternatives in this category on this page.</p>}
              {alts.map((a) => (
                <div key={a.id} className="flex items-center gap-3 rounded-xl border border-border bg-background p-3">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"><Package className="size-4" /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{a.name}</p>
                    <p className="text-xs text-muted-foreground">{a.quantity.toLocaleString()} in stock · {currency(a.price)}</p>
                  </div>
                  <Badge variant="neutral">{a.brand}</Badge>
                </div>
              ))}
            </div>
          </Section>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex flex-wrap gap-2 border-t border-border p-4">
          {isArchived ? (
            <>
              <Button variant="outline" className="flex-1" onClick={onClose}>Close</Button>
              {can("inventory.restore") && (
                <Button className="flex-1 gap-1.5" disabled={busy} onClick={() => void restoreProduct()}>
                  <ArchiveRestore className="size-4" /> {busy ? "Restoring…" : "Restore"}
                </Button>
              )}
            </>
          ) : (
            <>
              {can("inventory.update") ? (
                <Button variant="outline" className="flex-1 gap-1.5" onClick={() => setEditing((v) => !v)}><Pencil className="size-4" /> {editing ? "Cancel edit" : "Edit"}</Button>
              ) : (
                <Button variant="outline" className="flex-1" onClick={onClose}>Close</Button>
              )}
              {can("inventory.archive") && (
                <Button variant="outline" className="gap-1.5" disabled={busy} onClick={() => void archiveProduct()}>
                  <Archive className="size-4" /> Archive
                </Button>
              )}
              <Button className="flex-1 gap-1.5" onClick={() => router.push("/pos")}><ShoppingCart className="size-4" /> Sell</Button>
            </>
          )}
        </div>
      </div>
    </Overlay>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function Section({ title, icon: Icon, action, children }: { title: string; icon: typeof Package; action?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Icon className="size-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">{title}</h3>
        {action && <span className="ml-auto text-xs text-muted-foreground">{action}</span>}
      </div>
      {children}
    </div>
  )
}
