"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowRight, CheckCircle2, FileWarning, Search, Trash2, XCircle } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { ProductPicker } from "@/features/inventory/components/ProductPicker"
import { api, ApiError } from "@/lib/api/client"
import type { Page, Product, Sale, SaleCorrection } from "@/lib/api/types"
import { currency } from "@/lib/format"
import { useAuth } from "@/lib/auth-context"
import { notifyInventoryChanged } from "@/lib/inventory-sync"

type StatusFilter = "PENDING" | "APPROVED" | "REJECTED" | ""

const statusVariant = (status: string) =>
  status === "PENDING" ? "warning" : status === "APPROVED" ? "success" : "neutral"

const paymentLabel: Record<string, string> = { CASH: "Cash", CARD: "Card", MOBILE_MONEY: "Mobile money" }

function fmt(iso?: string | null) {
  return iso ? new Date(iso).toLocaleString() : "—"
}

export default function CorrectionsPage() {
  const { can, loading } = useAuth()
  const allowed = can("sales.correction_approve")
  const [filter, setFilter] = useState<StatusFilter>("PENDING")
  const [query, setQuery] = useState("")
  const [rows, setRows] = useState<SaleCorrection[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<SaleCorrection | null>(null)
  const [mode, setMode] = useState<"approve" | "reject" | null>(null)

  const load = useCallback(() => {
    if (!allowed) return
    const params = new URLSearchParams({ limit: "100" })
    if (filter) params.set("status", filter)
    if (query.trim()) params.set("q", query.trim())
    api<Page<SaleCorrection>>(`/sale-corrections?${params}`)
      .then((page) => {
        setRows(page.items)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load corrections"))
    Promise.all(
      (["PENDING", "APPROVED", "REJECTED"] as const).map((s) =>
        api<Page<SaleCorrection>>(`/sale-corrections?status=${s}&limit=1`).then((p) => [s, p.total] as const),
      ),
    )
      .then((pairs) => setCounts(Object.fromEntries(pairs)))
      .catch(() => undefined)
  }, [allowed, filter, query])

  useEffect(() => {
    const t = window.setTimeout(load, 200)
    return () => window.clearTimeout(t)
  }, [load])

  const loadDetail = useCallback((id: string) => {
    api<SaleCorrection>(`/sale-corrections/${id}`)
      .then(setDetail)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not open correction"))
  }, [])

  useEffect(() => {
    if (selectedId) loadDetail(selectedId)
    else setDetail(null)
  }, [selectedId, loadDetail])

  if (!loading && !allowed) {
    return (
      <>
        <AppTopbar title="Sale Corrections" />
        <div className="p-6 text-sm text-muted-foreground">Only administrators can review sale corrections.</div>
      </>
    )
  }

  return (
    <>
      <AppTopbar title="Sale Corrections" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-4 p-4 md:p-6">
        <div>
          <h2 className="text-xl font-semibold">Sale correction requests</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Staff request corrections from the Point of Sale sale lookup. Approving restocks the original sale and records a new corrected sale.
            Nothing is edited in place and cash totals are never changed silently.
          </p>
        </div>
        {error && <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        {notice && <p className="rounded-xl border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-primary">{notice}</p>}
        <div className="flex flex-wrap items-center gap-2">
          {(["PENDING", "APPROVED", "REJECTED", ""] as StatusFilter[]).map((s) => (
            <Button key={s || "all"} type="button" size="sm" variant={filter === s ? "default" : "outline"} onClick={() => setFilter(s)}>
              {s ? s.charAt(0) + s.slice(1).toLowerCase() : "All"}
              {s && counts[s] != null ? ` (${counts[s]})` : ""}
            </Button>
          ))}
          <div className="relative ml-auto w-full max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search sale #, CR reference, reason…"
              className="h-9 w-full rounded-lg border border-border bg-background pl-8 pr-3 text-sm outline-none"
            />
          </div>
        </div>
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <div className="overflow-x-auto rounded-2xl border border-border bg-card">
            {!rows.length ? (
              <p className="p-6 text-sm text-muted-foreground">No correction requests{filter ? ` with status ${filter.toLowerCase()}` : ""}.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Correction</th>
                    <th className="px-3 py-2 font-medium">Original sale</th>
                    <th className="px-3 py-2 font-medium">Requested by</th>
                    <th className="px-3 py-2 font-medium">Requested at</th>
                    <th className="px-3 py-2 font-medium">Reason</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => setSelectedId(row.id)}
                      className={`cursor-pointer hover:bg-muted/40 ${selectedId === row.id ? "bg-muted/60" : ""}`}
                    >
                      <td className="px-3 py-2 font-mono text-xs">{row.reference || row.id.slice(0, 8)}</td>
                      <td className="px-3 py-2">
                        <p className="font-mono text-xs">{row.sale_number}</p>
                        <p className="text-xs text-muted-foreground">{row.sale_total != null ? currency(Number(row.sale_total)) : ""}</p>
                      </td>
                      <td className="px-3 py-2">{row.requested_by_name ?? "—"}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">{fmt(row.created_at)}</td>
                      <td className="max-w-48 truncate px-3 py-2" title={row.reason}>{row.reason}</td>
                      <td className="px-3 py-2">
                        <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="rounded-2xl border border-border bg-card p-5">
            {!detail ? (
              <div className="flex h-full min-h-48 flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
                <FileWarning className="size-6" />
                Select a request to see the full original transaction.
              </div>
            ) : (
              <CorrectionDetail
                correction={detail}
                onApprove={() => setMode("approve")}
                onReject={() => setMode("reject")}
              />
            )}
          </div>
        </div>
      </div>
      {detail && mode === "reject" && (
        <RejectCorrection
          correction={detail}
          onClose={() => setMode(null)}
          onDone={() => {
            setMode(null)
            setNotice(`${detail.reference} rejected. The original sale is unchanged.`)
            loadDetail(detail.id)
            load()
          }}
        />
      )}
      {detail && mode === "approve" && (
        <ApproveCorrection
          correction={detail}
          onClose={() => setMode(null)}
          onDone={(result) => {
            setMode(null)
            setNotice(
              `${result.reference} approved. Refund ${result.return_number ?? ""} ${currency(Number(result.refund_amount ?? 0))}, corrected sale ${result.corrected_sale_number ?? ""} ${currency(Number(result.corrected_sale_total ?? 0))}.`,
            )
            notifyInventoryChanged()
            loadDetail(detail.id)
            load()
          }}
        />
      )}
    </>
  )
}

function SaleBlock({ sale, title }: { sale: Sale; title: string }) {
  return (
    <div className="rounded-xl border border-border">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border p-3">
        <div>
          <p className="text-xs uppercase text-muted-foreground">{title}</p>
          <p className="font-mono text-sm font-medium">{sale.sale_number}</p>
          <p className="text-xs text-muted-foreground">
            {fmt(sale.created_at)} · Cashier {sale.cashier_name ?? "—"} · Customer {sale.customer_name || "Walk-in"}
          </p>
        </div>
        <div className="text-right">
          <Badge variant={sale.status === "COMPLETED" ? "success" : "warning"}>{sale.status.replace("_", " ")}</Badge>
          <p className="mt-1 text-xs text-muted-foreground">{paymentLabel[sale.payment_method] ?? sale.payment_method}</p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Medicine</th>
              <th className="px-3 py-2 font-medium">Batch / expiry</th>
              <th className="px-3 py-2 text-right font-medium">Qty</th>
              <th className="px-3 py-2 text-right font-medium">Returned</th>
              <th className="px-3 py-2 text-right font-medium">Unit price</th>
              <th className="px-3 py-2 text-right font-medium">Line total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sale.items.map((item) => (
              <tr key={item.id}>
                <td className="px-3 py-2">
                  <p className="font-medium">{item.product_name}</p>
                  <p className="text-muted-foreground">{item.product_sku}</p>
                </td>
                <td className="px-3 py-2">
                  {item.batch_number ?? "—"}
                  {item.batch_expiry ? ` · ${item.batch_expiry}` : ""}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{item.quantity}</td>
                <td className="px-3 py-2 text-right tabular-nums">{item.quantity_returned}</td>
                <td className="px-3 py-2 text-right tabular-nums">{currency(Number(item.unit_price))}</td>
                <td className="px-3 py-2 text-right tabular-nums">{currency(Number(item.line_total))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border p-3 text-xs sm:grid-cols-4">
        <span className="text-muted-foreground">Subtotal</span>
        <span className="text-right tabular-nums">{currency(Number(sale.subtotal))}</span>
        <span className="text-muted-foreground">Discount ({Number(sale.discount_percent)}%)</span>
        <span className="text-right tabular-nums">-{currency(Number(sale.discount_amount))}</span>
        <span className="text-muted-foreground">Tax ({Number(sale.tax_rate)}%)</span>
        <span className="text-right tabular-nums">{currency(Number(sale.tax_amount))}</span>
        <span className="font-semibold">Total</span>
        <span className="text-right font-semibold tabular-nums">{currency(Number(sale.total))}</span>
      </div>
      <div className="border-t border-border px-3 py-2 text-right">
        <Link href={`/reports?tab=journal&sale=${sale.id}`} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
          Open in Sales Journal <ArrowRight className="size-3" />
        </Link>
      </div>
    </div>
  )
}

function CorrectionDetail({
  correction,
  onApprove,
  onReject,
}: {
  correction: SaleCorrection
  onApprove: () => void
  onReject: () => void
}) {
  const diff = correction.financial_difference != null ? Number(correction.financial_difference) : null
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-muted-foreground">{correction.reference}</p>
          <h3 className="text-lg font-semibold">Correction for {correction.sale_number}</h3>
        </div>
        <Badge variant={statusVariant(correction.status)}>{correction.status}</Badge>
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Requested by</dt>
        <dd>{correction.requested_by_name ?? "—"}</dd>
        <dt className="text-muted-foreground">Requested at</dt>
        <dd>{fmt(correction.created_at)}</dd>
        <dt className="text-muted-foreground">Reason</dt>
        <dd>{correction.reason}</dd>
        {correction.status !== "PENDING" && (
          <>
            <dt className="text-muted-foreground">{correction.status === "APPROVED" ? "Approved by" : "Rejected by"}</dt>
            <dd>{correction.reviewed_by_name ?? "—"}</dd>
            <dt className="text-muted-foreground">Reviewed at</dt>
            <dd>{fmt(correction.reviewed_at)}</dd>
            {correction.review_note && (
              <>
                <dt className="text-muted-foreground">{correction.status === "REJECTED" ? "Rejection reason" : "Review note"}</dt>
                <dd>{correction.review_note}</dd>
              </>
            )}
          </>
        )}
      </dl>
      {correction.status === "APPROVED" && (
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm">
          <p>
            Refund {correction.return_number}: <span className="font-medium">{currency(Number(correction.refund_amount ?? 0))}</span> ·
            Corrected sale {correction.corrected_sale_number}: <span className="font-medium">{currency(Number(correction.corrected_sale_total ?? 0))}</span>
          </p>
          {diff != null && (
            <p className="mt-1">
              Financial difference: <span className="font-semibold">{currency(diff)}</span>{" "}
              <span className="text-muted-foreground">
                {diff > 0 ? "(customer owed the pharmacy this amount)" : diff < 0 ? "(pharmacy owed the customer this amount)" : "(no difference)"}
              </span>
            </p>
          )}
        </div>
      )}
      {correction.sale && <SaleBlock sale={correction.sale} title="Original sale" />}
      {correction.corrected_sale && <SaleBlock sale={correction.corrected_sale} title="Corrected sale" />}
      {correction.status === "PENDING" && (
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="gap-1.5" onClick={onReject}>
            <XCircle className="size-4" /> Reject
          </Button>
          <Button type="button" className="gap-1.5" onClick={onApprove}>
            <CheckCircle2 className="size-4" /> Review corrected cart & approve
          </Button>
        </div>
      )}
    </div>
  )
}

function RejectCorrection({
  correction,
  onClose,
  onDone,
}: {
  correction: SaleCorrection
  onClose: () => void
  onDone: () => void
}) {
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <Overlay onClose={onClose}>
      <form
        className="w-full max-w-md space-y-3 rounded-2xl border border-border bg-card p-6"
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault()
          if (!reason.trim()) {
            setError("A rejection reason is required")
            return
          }
          setBusy(true)
          try {
            await api(`/sale-corrections/${correction.id}/reject`, { method: "POST", body: JSON.stringify({ reason: reason.trim() }) })
            onDone()
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Reject failed")
          } finally {
            setBusy(false)
          }
        }}
      >
        <h2 className="text-lg font-semibold">Reject {correction.reference}</h2>
        <p className="text-sm text-muted-foreground">
          {correction.sale_number} · requested because: {correction.reason}. The original sale and stock stay unchanged.
        </p>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="Why is this request rejected? (required)" className="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={busy}>{busy ? "Rejecting…" : "Reject request"}</Button>
        </div>
      </form>
    </Overlay>
  )
}

type CartLine = { key: string; product: { id: string; name: string; sku?: string } | null; quantity: string }

function ApproveCorrection({
  correction,
  onClose,
  onDone,
}: {
  correction: SaleCorrection
  onClose: () => void
  onDone: (result: SaleCorrection) => void
}) {
  const sale = correction.sale
  const [catalog, setCatalog] = useState<Record<string, Product>>({})
  const [lines, setLines] = useState<CartLine[]>(() => {
    const qtyByProduct = new Map<string, { name: string; sku?: string; qty: number }>()
    for (const item of sale?.items ?? []) {
      const remaining = item.quantity - item.quantity_returned
      if (remaining <= 0) continue
      const prev = qtyByProduct.get(item.product_id)
      qtyByProduct.set(item.product_id, {
        name: item.product_name ?? "Medicine",
        sku: item.product_sku ?? undefined,
        qty: (prev?.qty ?? 0) + remaining,
      })
    }
    const initial = [...qtyByProduct.entries()].map(([id, v]) => ({
      key: crypto.randomUUID(),
      product: { id, name: v.name, sku: v.sku },
      quantity: String(v.qty),
    }))
    return initial.length ? initial : [{ key: crypto.randomUUID(), product: null, quantity: "1" }]
  })
  const [pay, setPay] = useState(sale?.payment_method || "CASH")
  const [discount, setDiscount] = useState(Number(sale?.discount_percent || 0))
  const [note, setNote] = useState("")
  const [confirm, setConfirm] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [idem] = useState(() => crypto.randomUUID())

  const returnedQty = useMemo(() => {
    const map: Record<string, number> = {}
    for (const item of sale?.items ?? []) map[item.product_id] = (map[item.product_id] ?? 0) + item.quantity - item.quantity_returned
    return map
  }, [sale])

  useEffect(() => {
    const ids = [...new Set(lines.map((l) => l.product?.id).filter((id): id is string => !!id && !catalog[id]))]
    if (!ids.length) return
    Promise.all(ids.map((id) => api<Product>(`/products/${id}`).catch(() => null))).then((found) => {
      setCatalog((current) => {
        const next = { ...current }
        for (const p of found) if (p) next[p.id] = p
        return next
      })
    })
  }, [lines, catalog])

  const taxRate = Number(sale?.tax_rate || 0)
  const subtotal = lines.reduce((sum, l) => {
    const p = l.product ? catalog[l.product.id] : undefined
    return sum + (p ? Number(p.selling_price) * (Number(l.quantity) || 0) : 0)
  }, 0)
  const discountAmt = (subtotal * discount) / 100
  const estTotal = (subtotal - discountAmt) * (1 + taxRate / 100)
  const refundableEstimate = (sale?.items ?? []).reduce((sum, item) => {
    const remaining = item.quantity - item.quantity_returned
    if (remaining <= 0 || !item.quantity) return sum
    return sum + (Number(item.line_total) / item.quantity) * remaining
  }, 0)
  const refundEstimate =
    refundableEstimate * (1 - Number(sale?.discount_percent || 0) / 100) * (1 + Number(sale?.tax_rate || 0) / 100)
  const estDiff = estTotal - refundEstimate

  const setLine = (key: string, patch: Partial<CartLine>) =>
    setLines((c) => c.map((l) => (l.key === key ? { ...l, ...patch } : l)))

  const submit = async () => {
    const items = lines
      .filter((l) => l.product && Number(l.quantity) > 0)
      .map((l) => ({ product_id: l.product!.id, quantity: Number(l.quantity) }))
    if (!items.length) {
      setError("The corrected cart needs at least one medicine")
      return
    }
    if (lines.some((l) => l.product && (!Number.isInteger(Number(l.quantity)) || Number(l.quantity) <= 0))) {
      setError("Quantities must be whole numbers above 0")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await api<SaleCorrection>(`/sale-corrections/${correction.id}/approve`, {
        method: "POST",
        body: JSON.stringify({
          items,
          payment_method: pay,
          discount_percent: discount,
          tax_rate: sale?.tax_rate,
          idempotency_key: idem,
          review_note: note.trim(),
          notes: `Correction ${correction.reference} of ${correction.sale_number}`,
        }),
      })
      onDone(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Approve failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Overlay onClose={onClose}>
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-2xl border border-border bg-card" onClick={(e) => e.stopPropagation()}>
        <div className="space-y-1 border-b border-border p-5">
          <h2 className="text-lg font-semibold">Approve {correction.reference}</h2>
          <p className="text-sm text-muted-foreground">
            The cart below starts as a copy of the original {correction.sale_number}. Change medicines or quantities to what the customer actually received.
            On approval, all remaining items of the original sale are returned and restocked, and this cart is recorded as a new sale, in one step.
          </p>
          <p className="text-xs text-muted-foreground">Reason given: {correction.reason}</p>
        </div>
        <div className="space-y-3 overflow-y-auto p-5">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="pb-2 font-medium">Corrected medicine</th>
                <th className="pb-2 font-medium">Qty</th>
                <th className="pb-2 text-right font-medium">Current price</th>
                <th className="pb-2 text-right font-medium">Available*</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {lines.map((line) => {
                const p = line.product ? catalog[line.product.id] : undefined
                const available = p ? p.quantity_on_hand + (returnedQty[p.id] ?? 0) : null
                const short = available != null && Number(line.quantity) > available
                return (
                  <tr key={line.key}>
                    <td className="py-2 pr-2">
                      <ProductPicker
                        value={line.product}
                        onSelect={(prod) => {
                          setCatalog((c) => ({ ...c, [prod.id]: prod }))
                          setLine(line.key, { product: { id: prod.id, name: prod.name, sku: prod.sku } })
                        }}
                        onClear={() => setLine(line.key, { product: null })}
                        placeholder="Search medicine…"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <input
                        type="number"
                        min={1}
                        step={1}
                        value={line.quantity}
                        onChange={(e) => setLine(line.key, { quantity: e.target.value })}
                        className="h-9 w-20 rounded-lg border border-border px-2 text-sm"
                        aria-label="Quantity"
                      />
                    </td>
                    <td className="py-2 text-right tabular-nums">{p ? currency(Number(p.selling_price)) : "—"}</td>
                    <td className={`py-2 text-right tabular-nums ${short ? "text-destructive" : ""}`}>{available ?? "—"}</td>
                    <td className="py-2 pl-2 text-right">
                      <button
                        type="button"
                        aria-label="Remove line"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={() => setLines((c) => (c.length === 1 ? [{ key: crypto.randomUUID(), product: null, quantity: "1" }] : c.filter((l) => l.key !== line.key)))}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <Button type="button" size="sm" variant="outline" onClick={() => setLines((c) => [...c, { key: crypto.randomUUID(), product: null, quantity: "1" }])}>
            Add line
          </Button>
          <p className="text-xs text-muted-foreground">
            *Available = current stock plus the quantity that will be restocked from the original sale. Batches are allocated first-expiry-first at approval.
            Prices are the current selling prices.
          </p>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2">
              Payment
              <select value={pay} onChange={(e) => setPay(e.target.value)} className="h-9 rounded-lg border border-border px-2">
                <option value="CASH">Cash</option>
                <option value="CARD">Card</option>
                <option value="MOBILE_MONEY">Mobile money</option>
              </select>
            </label>
            <label className="flex items-center gap-2">
              Discount %
              <input type="number" min={0} max={100} value={discount} onChange={(e) => setDiscount(Number(e.target.value) || 0)} className="h-9 w-16 rounded-lg border border-border px-2" />
            </label>
            <span className="text-muted-foreground">Tax {taxRate}% (from original sale)</span>
          </div>
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="Approval note (optional)" className="h-9 w-full rounded-lg border border-border px-3 text-sm" />
          <div className="rounded-xl border border-border bg-muted/30 p-3 text-sm">
            <div className="flex justify-between"><span>Estimated refund of original</span><span className="tabular-nums">{currency(refundEstimate)}</span></div>
            <div className="flex justify-between"><span>Estimated corrected sale total</span><span className="tabular-nums">{currency(estTotal)}</span></div>
            <div className="mt-1 flex justify-between border-t border-border pt-1 font-semibold">
              <span>Estimated difference</span>
              <span className="tabular-nums">{currency(estDiff)}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Positive: collect this from the customer. Negative: give this back. Final figures are calculated by the server and shown after approval.
            </p>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} className="mt-1" />
            I confirm returning and restocking the original sale and recording this corrected sale.
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-border p-5">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="button" disabled={busy || !confirm} onClick={submit}>
            {busy ? "Approving…" : "Approve & record corrected sale"}
          </Button>
        </div>
      </div>
    </Overlay>
  )
}
