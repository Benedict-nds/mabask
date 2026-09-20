"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Plus, Star, Mail, Truck, Sparkles, Building2, Clock, Trash2, FileUp, Download } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { api, ApiError } from "@/lib/api/client"
import type { Page, Product, PurchaseOrder, Supplier } from "@/lib/api/types"
import { currency, normalizeExpiryInput } from "@/lib/format"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"

const statusMeta: Record<string, { label: string; variant: "success" | "neutral" | "warning" }> = {
  preferred: { label: "Preferred", variant: "success" },
  active: { label: "Active", variant: "neutral" },
  review: { label: "Needs review", variant: "warning" },
  inactive: { label: "Inactive", variant: "neutral" },
}

export default function SuppliersPage() {
  const { can } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const prefillId = searchParams.get("create")
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [pos, setPos] = useState<PurchaseOrder[]>([])
  const [adding, setAdding] = useState(false)
  const [creatingPo, setCreatingPo] = useState(false)
  const [prefillProductId, setPrefillProductId] = useState<string | null>(null)
  const [receiving, setReceiving] = useState<PurchaseOrder | null>(null)
  const [viewing, setViewing] = useState<PurchaseOrder | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = () => {
    api<Supplier[]>("/suppliers").then(setSuppliers).catch((e) => setError(e.message))
    api<PurchaseOrder[]>("/purchase-orders").then(setPos).catch(() => setPos([]))
  }
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (!prefillId) return
    setPrefillProductId(prefillId)
    setCreatingPo(true)
  }, [prefillId])

  const closeCreate = () => {
    setCreatingPo(false)
    setPrefillProductId(null)
    if (prefillId) router.replace("/suppliers")
  }

  const totalOutstanding = suppliers.reduce((a, s) => a + Number(s.outstanding), 0)
  const avgOnTime = suppliers.length ? Math.round(suppliers.reduce((a, s) => a + s.on_time_rate, 0) / suppliers.length) : 0

  return (
    <>
      <AppTopbar title="Suppliers" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1 rounded-xl border border-border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground">Active suppliers</p>
            <p className="mt-0.5 text-xl font-semibold">{suppliers.length}</p>
          </div>
          <div className="flex-1 rounded-xl border border-border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground">Open PO value</p>
            <p className="mt-0.5 text-xl font-semibold text-destructive">{currency(totalOutstanding)}</p>
          </div>
          <div className="flex-1 rounded-xl border border-border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground">Avg. on-time rate</p>
            <p className="mt-0.5 text-xl font-semibold text-primary">{avgOnTime}%</p>
          </div>
          {can("suppliers.create") && <Button className="h-11 gap-1.5" onClick={() => setAdding(true)}><Plus className="size-4" /> Add supplier</Button>}
          {can("purchases.create") && <Button variant="outline" className="h-11 gap-1.5" onClick={() => setCreatingPo(true)}><Plus className="size-4" /> Create PO</Button>}
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {notice && <p className="text-sm text-primary">{notice}</p>}
        <div className="flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary/5 p-4">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary"><Sparkles className="size-4" /></span>
          <p className="text-sm leading-relaxed">
            <span className="font-semibold text-primary">Purchasing: </span>
            {pos.length} purchase orders on file. Click a PO number to review line items before you submit or approve.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {suppliers.map((s) => {
            const meta = statusMeta[s.status] ?? statusMeta.active
            return (
              <div key={s.id} className="flex flex-col rounded-2xl border border-border bg-card p-5">
                <div className="flex items-start gap-3">
                  <span className="flex size-11 items-center justify-center rounded-xl bg-secondary/10 text-secondary"><Building2 className="size-5" /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{s.name}</p>
                    <p className="text-xs text-muted-foreground">{s.contact_name}</p>
                  </div>
                  <Badge variant={meta.variant}>{meta.label}</Badge>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <Metric icon={Star} label="Rating" value={Number(s.rating).toFixed(1)} accent="text-warning-foreground" />
                  <Metric icon={Truck} label="On-time" value={`${s.on_time_rate}%`} accent={s.on_time_rate >= 90 ? "text-primary" : "text-warning-foreground"} />
                  <Metric icon={Building2} label="Active SKUs" value={String(s.active_skus)} />
                  <Metric icon={Clock} label="Last delivery" value={s.last_delivery ? new Date(s.last_delivery).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "—"} />
                </div>
                <div className="mt-4 flex items-center justify-between rounded-xl border border-border bg-background px-3 py-2.5">
                  <span className="text-xs text-muted-foreground">Open POs</span>
                  <span className={cn("text-sm font-semibold", Number(s.outstanding) > 0 ? "text-destructive" : "text-primary")}>{Number(s.outstanding) > 0 ? currency(Number(s.outstanding)) : "Settled"}</span>
                </div>
                {s.email && (
                  <a href={`mailto:${s.email}`} className="mt-4 inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-border text-sm">
                    <Mail className="size-3.5" /> {s.email}
                  </a>
                )}
              </div>
            )
          })}
        </div>
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold">Purchase orders</h3>
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-2">PO</th><th>Supplier</th><th>Status</th><th className="text-right">Total</th><th />
              </tr>
            </thead>
            <tbody>
              {pos.map((po) => (
                <tr key={po.id} className="border-t border-border">
                  <td className="py-2">
                    <button className="font-mono text-xs text-primary hover:underline" onClick={() => setViewing(po)}>{po.po_number}</button>
                  </td>
                  <td>{po.supplier_name}</td>
                  <td><Badge variant="neutral">{po.status}</Badge></td>
                  <td className="text-right">{currency(Number(po.total))}</td>
                  <td className="space-x-2 text-right">
                    <Button size="sm" variant="ghost" onClick={() => setViewing(po)}>View</Button>
                    <Button size="sm" variant="ghost" onClick={() => exportPoCsv(po)}>CSV</Button>
                    {po.status === "DRAFT" && can("purchases.create") && (
                      <Button size="sm" variant="outline" onClick={async () => { await api(`/purchase-orders/${po.id}/submit`, { method: "POST" }); setNotice("PO submitted"); load() }}>Submit</Button>
                    )}
                    {(po.status === "DRAFT" || po.status === "SUBMITTED") && can("purchases.approve") && (
                      <Button size="sm" onClick={async () => { await api(`/purchase-orders/${po.id}/approve`, { method: "POST" }); setNotice("PO approved"); load() }}>Approve</Button>
                    )}
                    {(po.status === "APPROVED" || po.status === "PARTIALLY_RECEIVED") && can("purchases.receive") && (
                      <Button size="sm" variant="outline" onClick={() => setReceiving(po)}>Receive</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {adding && <AddSupplier onClose={() => setAdding(false)} onSaved={() => { setAdding(false); load() }} />}
      {creatingPo && (
        <CreatePO
          suppliers={suppliers}
          productId={prefillProductId}
          onClose={closeCreate}
          onSaved={() => { closeCreate(); setNotice("Purchase order created"); load() }}
        />
      )}
      {receiving && <ReceivePO po={receiving} onClose={() => setReceiving(null)} onSaved={() => { setReceiving(null); setNotice("Stock received"); load() }} />}
      {viewing && (
        <ViewPO
          po={viewing}
          canSubmit={can("purchases.create")}
          canApprove={can("purchases.approve")}
          canReceive={can("purchases.receive")}
          onClose={() => setViewing(null)}
          onChanged={(note) => { setViewing(null); setNotice(note); load() }}
          onReceive={() => { setReceiving(viewing); setViewing(null) }}
        />
      )}
    </>
  )
}

function Metric({ icon: Icon, label, value, accent }: { icon: typeof Star; label: string; value: string; accent?: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"><Icon className="size-4" /></span>
      <div className="leading-tight">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={cn("font-semibold", accent)}>{value}</p>
      </div>
    </div>
  )
}

function AddSupplier({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [error, setError] = useState<string | null>(null)
  return (
    <Overlay onClose={onClose}>
      <form
        className="w-full max-w-md space-y-3 rounded-2xl border border-border bg-card p-6"
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault()
          const fd = new FormData(e.currentTarget)
          try {
            await api("/suppliers", { method: "POST", body: JSON.stringify({ name: fd.get("name"), contact_name: fd.get("contact"), email: fd.get("email"), phone: fd.get("phone") }) })
            onSaved()
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not save")
          }
        }}
      >
        <h2 className="text-lg font-semibold">Add supplier</h2>
        {["name", "contact", "email", "phone"].map((n) => (
          <input key={n} name={n} required={n === "name"} placeholder={n} className="h-10 w-full rounded-lg border border-border px-3 text-sm" />
        ))}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </Overlay>
  )
}

type POLine = {
  key: string
  product_id: string
  quantity: string
  unit_cost: string
  batch_number: string
  expiry_date: string
}

function csvCell(value: string | number | null | undefined) {
  const text = String(value ?? "")
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function exportPoCsv(po: PurchaseOrder) {
  const header = "name,quantity,unit_cost,batch,expiry,quantity_received,line_total"
  const rows = po.items.map((item) => [
    csvCell(item.product_name),
    item.quantity_ordered,
    item.unit_cost,
    csvCell(item.batch_number),
    item.expiry_date ?? "",
    item.quantity_received,
    (Number(item.unit_cost) * item.quantity_ordered).toFixed(2),
  ].join(","))
  downloadText(
    `${po.po_number}.csv`,
    [header, ...rows, "", `total,,,,,${Number(po.total).toFixed(2)}`].join("\n") + "\n",
    "text/csv;charset=utf-8",
  )
}

function exportPoText(po: PurchaseOrder) {
  const created = new Date(po.created_at).toLocaleString()
  const lines = [
    `AetherQore purchase order`,
    `PO: ${po.po_number}`,
    `Status: ${po.status}`,
    `Supplier: ${po.supplier_name ?? po.supplier_id}`,
    `Created: ${created}`,
    po.notes ? `Notes: ${po.notes}` : "",
    "",
    "Items",
    "-----",
    ...po.items.map((item) => {
      const line = (Number(item.unit_cost) * item.quantity_ordered).toFixed(2)
      return [
        `${item.product_name}`,
        `  Qty ordered: ${item.quantity_ordered}  Received: ${item.quantity_received}`,
        `  Unit cost: ${currency(Number(item.unit_cost))}  Line: ${currency(Number(line))}`,
        item.batch_number ? `  Batch: ${item.batch_number}` : "",
        item.expiry_date ? `  Expiry: ${item.expiry_date}` : "",
      ].filter(Boolean).join("\n")
    }),
    "",
    `Total: ${currency(Number(po.total))}`,
    "",
  ].filter((line) => line !== undefined)
  downloadText(`${po.po_number}.txt`, lines.join("\n"), "text/plain;charset=utf-8")
}

function emptyLine(): POLine {
  return { key: crypto.randomUUID(), product_id: "", quantity: "1", unit_cost: "", batch_number: "", expiry_date: "" }
}

function parsePurchaseCsv(text: string): { name: string; quantity: string; unit_cost: string; batch: string; expiry: string }[] {
  const rows = text.replace(/^\uFEFF/, "").trim().split(/\r?\n/).filter(Boolean)
  if (rows.length < 2) return []
  const headers = rows[0].split(",").map((h) => h.trim().toLowerCase().replace(/"/g, ""))
  const idx = (names: string[]) => names.map((n) => headers.indexOf(n)).find((i) => i >= 0) ?? -1
  const nameI = idx(["name", "medicine", "product"])
  const qtyI = idx(["quantity", "qty"])
  const costI = idx(["unit_cost", "cost", "price"])
  const batchI = idx(["batch", "batch_number"])
  const expiryI = idx(["expiry", "expiry_date"])
  if (nameI < 0 || qtyI < 0) return []
  return rows.slice(1).flatMap((row) => {
    const cols = row.split(",").map((c) => c.trim().replace(/^"|"$/g, ""))
    const name = cols[nameI] || ""
    if (!name) return []
    return [{
      name,
      quantity: cols[qtyI] || "1",
      unit_cost: costI >= 0 ? cols[costI] || "" : "",
      batch: batchI >= 0 ? cols[batchI] || "" : "",
      expiry: expiryI >= 0 ? cols[expiryI] || "" : "",
    }]
  })
}

function CreatePO({
  suppliers,
  productId,
  onClose,
  onSaved,
}: {
  suppliers: Supplier[]
  productId?: string | null
  onClose: () => void
  onSaved: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [products, setProducts] = useState<Product[]>([])
  const [supplierId, setSupplierId] = useState("")
  const [notes, setNotes] = useState("")
  const [lines, setLines] = useState<POLine[]>([emptyLine()])

  useEffect(() => {
    api<Page<Product>>("/products?limit=200").then(async (page) => {
      let items = page.items
      let product = productId ? items.find((p) => p.id === productId) : undefined
      if (productId && !product) {
        try {
          product = await api<Product>(`/products/${productId}`)
          items = [...items, product]
        } catch { /* ignore */ }
      }
      setProducts(items)
      if (!product) return
      setLines([{
        key: crypto.randomUUID(),
        product_id: product.id,
        quantity: String(Math.max(product.reorder_threshold - product.quantity_on_hand, 1)),
        unit_cost: String(product.cost_price),
        batch_number: "",
        expiry_date: "",
      }])
      if (product.supplier_id) setSupplierId(product.supplier_id)
      else {
        const preferred = suppliers.find((s) => s.status === "preferred")
        if (preferred) setSupplierId(preferred.id)
      }
    }).catch(() => setProducts([]))
  }, [productId, suppliers])

  const updateLine = (key: string, patch: Partial<POLine>) => {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)))
  }

  const addProducts = (incoming: Product[], qtyFor?: (p: Product) => string) => {
    setLines((current) => {
      const next = [...current.filter((line) => line.product_id)]
      for (const product of incoming) {
        if (next.some((line) => line.product_id === product.id)) continue
        next.push({
          key: crypto.randomUUID(),
          product_id: product.id,
          quantity: qtyFor ? qtyFor(product) : "1",
          unit_cost: String(product.cost_price),
          batch_number: "",
          expiry_date: "",
        })
      }
      return next.length ? next : [emptyLine()]
    })
  }

  const importCsv = async (file: File) => {
    const text = await file.text()
    const rows = parsePurchaseCsv(text)
    if (!rows.length) {
      setError("CSV needs columns name,quantity,unit_cost (optional batch,expiry)")
      return
    }
    const unmatched: string[] = []
    const mapped: POLine[] = []
    for (const row of rows) {
      const needle = row.name.toLowerCase()
      const product = products.find((p) => p.name.toLowerCase() === needle)
        || products.find((p) => p.barcode === row.name || p.sku.toLowerCase() === needle)
        || products.find((p) => p.name.toLowerCase().includes(needle) || needle.includes(p.name.toLowerCase()))
      if (!product) {
        unmatched.push(row.name)
        continue
      }
      mapped.push({
        key: crypto.randomUUID(),
        product_id: product.id,
        quantity: row.quantity || "1",
        unit_cost: row.unit_cost || String(product.cost_price),
        batch_number: row.batch,
        expiry_date: row.expiry ? normalizeExpiryInput(row.expiry) : "",
      })
    }
    if (!mapped.length) {
      setError(`No products matched: ${unmatched.slice(0, 4).join(", ")}`)
      return
    }
    setLines(mapped)
    setError(unmatched.length ? `Imported ${mapped.length} lines. Unmatched: ${unmatched.join(", ")}` : null)
  }

  const addLowStock = async () => {
    try {
      const [low, critical] = await Promise.all([
        api<Page<Product>>("/products?status=low&limit=200"),
        api<Page<Product>>("/products?status=critical&limit=200"),
      ])
      const needed = [...critical.items, ...low.items]
      if (!needed.length) {
        setError("No low-stock medicines to add")
        return
      }
      addProducts(needed, (p) => String(Math.max(p.reorder_threshold - p.quantity_on_hand, 1)))
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load low stock")
    }
  }

  const items = lines.flatMap((line) => {
    const product = products.find((p) => p.id === line.product_id)
    const qty = Number(line.quantity)
    if (!product || !qty) return []
    return [{
      product_id: product.id,
      product_name: product.name,
      quantity_ordered: qty,
      unit_cost: line.unit_cost || product.cost_price,
      batch_number: line.batch_number,
      expiry_date: line.expiry_date ? normalizeExpiryInput(line.expiry_date) : null,
    }]
  })
  const total = items.reduce((sum, item) => sum + Number(item.unit_cost) * item.quantity_ordered, 0)

  return (
    <Overlay onClose={onClose}>
      <form
        className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-2xl border border-border bg-card"
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault()
          if (!supplierId) {
            setError("Select a supplier")
            return
          }
          if (!items.length) {
            setError("Add at least one medicine with a quantity")
            return
          }
          setSaving(true)
          try {
            await api("/purchase-orders", {
              method: "POST",
              body: JSON.stringify({ supplier_id: supplierId, notes, items }),
            })
            onSaved()
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not create PO")
          } finally {
            setSaving(false)
          }
        }}
      >
        <div className="space-y-1 border-b border-border p-6 pb-4">
          <h2 className="text-lg font-semibold">Create purchase order</h2>
          <p className="text-sm text-muted-foreground">
            {productId
              ? "This medicine is already on the order with a suggested restock quantity. Pick a supplier and save."
              : "One order can include many medicines. Import a CSV if you already have the list."}
          </p>
        </div>
        <div className="space-y-3 overflow-y-auto p-6">
          <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} required className="h-10 w-full rounded-lg border border-border px-3 text-sm">
            <option value="">Supplier</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => setLines((c) => [...c, emptyLine()])}>
              <Plus className="size-3.5" /> Add medicine
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={addLowStock}>Add low-stock items</Button>
            <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-medium hover:bg-muted">
              <FileUp className="size-3.5" /> Import CSV
              <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) void importCsv(file); e.target.value = "" }} />
            </label>
            <a
              className="inline-flex h-8 items-center text-xs text-muted-foreground underline"
              href={`data:text/csv,${encodeURIComponent("name,quantity,unit_cost,batch,expiry\nParacetamol 500mg,1200,0.05,PCM-9925,2027-08-15\nAmoxicillin 500mg,500,0.18,AMX-2240,2027-04-01\n")}`}
              download="purchase-order-template.csv"
            >
              Download template
            </a>
          </div>
          <div className="overflow-hidden rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Medicine</th>
                  <th className="px-3 py-2 font-medium">Qty</th>
                  <th className="px-3 py-2 font-medium">Unit cost</th>
                  <th className="px-3 py-2 font-medium">Batch</th>
                  <th className="px-3 py-2 font-medium">Expiry</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {lines.map((line) => (
                  <tr key={line.key}>
                    <td className="px-2 py-2">
                      <select
                        value={line.product_id}
                        onChange={(e) => {
                          const product = products.find((p) => p.id === e.target.value)
                          updateLine(line.key, { product_id: e.target.value, unit_cost: product ? String(product.cost_price) : line.unit_cost })
                        }}
                        className="h-9 w-full min-w-48 rounded-lg border border-border px-2 text-sm"
                      >
                        <option value="">Select medicine</option>
                        {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-2"><input value={line.quantity} onChange={(e) => updateLine(line.key, { quantity: e.target.value })} type="number" min={1} className="h-9 w-20 rounded-lg border border-border px-2 text-sm" /></td>
                    <td className="px-2 py-2"><input value={line.unit_cost} onChange={(e) => updateLine(line.key, { unit_cost: e.target.value })} className="h-9 w-24 rounded-lg border border-border px-2 text-sm" /></td>
                    <td className="px-2 py-2"><input value={line.batch_number} onChange={(e) => updateLine(line.key, { batch_number: e.target.value })} className="h-9 w-24 rounded-lg border border-border px-2 text-sm" /></td>
                    <td className="px-2 py-2"><input value={line.expiry_date} onChange={(e) => updateLine(line.key, { expiry_date: e.target.value })} type="date" min="2000-01-01" max="2099-12-31" className="h-9 rounded-lg border border-border px-2 text-sm" /></td>
                    <td className="px-2 py-2">
                      <button type="button" className="text-muted-foreground hover:text-destructive" onClick={() => setLines((c) => (c.length === 1 ? [emptyLine()] : c.filter((l) => l.key !== line.key)))} aria-label="Remove line">
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes for this order" className="h-10 w-full rounded-lg border border-border px-3 text-sm" />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-border p-6 pt-4">
          <p className="text-sm text-muted-foreground">{items.length} medicine{items.length === 1 ? "" : "s"} · {currency(total)}</p>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Create draft"}</Button>
          </div>
        </div>
      </form>
    </Overlay>
  )
}

function ViewPO({
  po,
  canSubmit,
  canApprove,
  canReceive,
  onClose,
  onChanged,
  onReceive,
}: {
  po: PurchaseOrder
  canSubmit: boolean
  canApprove: boolean
  canReceive: boolean
  onClose: () => void
  onChanged: (note: string) => void
  onReceive: () => void
}) {
  const [detail, setDetail] = useState<PurchaseOrder>(po)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<PurchaseOrder>(`/purchase-orders/${po.id}`).then(setDetail).catch(() => setDetail(po))
  }, [po])

  const act = async (path: string, note: string) => {
    setBusy(true)
    setError(null)
    try {
      await api(`/purchase-orders/${detail.id}/${path}`, { method: "POST" })
      onChanged(note)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Overlay onClose={onClose}>
      <div className="w-full max-w-2xl space-y-4 rounded-2xl border border-border bg-card p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-muted-foreground">{detail.po_number}</p>
            <h2 className="text-lg font-semibold">{detail.supplier_name ?? "Purchase order"}</h2>
            <p className="text-sm text-muted-foreground">{detail.notes || "No notes"} · {new Date(detail.created_at).toLocaleString()}</p>
          </div>
          <Badge variant="neutral">{detail.status}</Badge>
        </div>
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Product</th>
                <th className="px-3 py-2 font-medium">Batch</th>
                <th className="px-3 py-2 text-right font-medium">Ordered</th>
                <th className="px-3 py-2 text-right font-medium">Received</th>
                <th className="px-3 py-2 text-right font-medium">Unit cost</th>
                <th className="px-3 py-2 text-right font-medium">Line</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {detail.items.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-2">
                    <p className="font-medium">{item.product_name}</p>
                    {item.expiry_date && <p className="text-xs text-muted-foreground">Expiry {item.expiry_date}</p>}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{item.batch_number || "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{item.quantity_ordered}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{item.quantity_received}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{currency(Number(item.unit_cost))}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{currency(Number(item.unit_cost) * item.quantity_ordered)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">{detail.items.length} line{detail.items.length === 1 ? "" : "s"}</span>
          <span className="font-semibold">Total {currency(Number(detail.total))}</span>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="gap-1.5" onClick={() => exportPoCsv(detail)}>
            <Download className="size-3.5" /> Export CSV
          </Button>
          <Button type="button" variant="outline" className="gap-1.5" onClick={() => exportPoText(detail)}>
            <Download className="size-3.5" /> Export text
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>Close</Button>
          {detail.status === "DRAFT" && canSubmit && (
            <Button variant="outline" disabled={busy} onClick={() => act("submit", "PO submitted")}>Submit</Button>
          )}
          {(detail.status === "DRAFT" || detail.status === "SUBMITTED") && canApprove && (
            <Button disabled={busy} onClick={() => act("approve", "PO approved")}>Approve</Button>
          )}
          {(detail.status === "APPROVED" || detail.status === "PARTIALLY_RECEIVED") && canReceive && (
            <Button variant="outline" onClick={onReceive}>Receive</Button>
          )}
        </div>
      </div>
    </Overlay>
  )
}

function ReceivePO({ po, onClose, onSaved }: { po: PurchaseOrder; onClose: () => void; onSaved: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  return (
    <Overlay onClose={onClose}>
      <form
        className="w-full max-w-lg space-y-3 rounded-2xl border border-border bg-card p-6"
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault()
          const fd = new FormData(e.currentTarget)
          const lines = po.items
            .map((item) => ({
              item_id: item.id,
              quantity: Number(fd.get(`qty-${item.id}`) || 0),
              batch_number: String(fd.get(`batch-${item.id}`) || item.batch_number || ""),
              expiry_date: normalizeExpiryInput(String(fd.get(`expiry-${item.id}`) || item.expiry_date || "")) || null,
            }))
            .filter((line) => line.quantity > 0)
          if (!lines.length) {
            setError("Enter a quantity to receive")
            return
          }
          setSaving(true)
          try {
            await api(`/purchase-orders/${po.id}/receive`, { method: "POST", body: JSON.stringify({ lines }) })
            onSaved()
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Receive failed")
          } finally {
            setSaving(false)
          }
        }}
      >
        <h2 className="text-lg font-semibold">Receive {po.po_number}</h2>
        {po.items.map((item) => {
          const remaining = item.quantity_ordered - item.quantity_received
          return (
            <div key={item.id} className="space-y-2 rounded-xl border border-border p-3">
              <p className="text-sm font-medium">{item.product_name} · remaining {remaining}</p>
              <div className="grid grid-cols-3 gap-2">
                <input name={`qty-${item.id}`} type="number" min={0} max={remaining} defaultValue={remaining} className="h-9 rounded-lg border border-border px-3 text-sm" />
                <input name={`batch-${item.id}`} defaultValue={item.batch_number} placeholder="Batch" className="h-9 rounded-lg border border-border px-3 text-sm" />
                <input name={`expiry-${item.id}`} type="date" min="2000-01-01" max="2099-12-31" defaultValue={item.expiry_date ?? ""} className="h-9 rounded-lg border border-border px-3 text-sm" />
              </div>
            </div>
          )
        })}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>{saving ? "Receiving…" : "Receive stock"}</Button>
        </div>
      </form>
    </Overlay>
  )
}
