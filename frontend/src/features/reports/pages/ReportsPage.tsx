"use client"

import { useEffect, useMemo, useState } from "react"
import { Sparkles, DollarSign, Percent, Wallet, Package, Download, ChevronLeft, ChevronRight, Search } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { BarChart, DonutChart } from "@/components/charts"
import { Overlay } from "@/components/ui/dismissable"
import { ProductPicker } from "@/features/inventory/components/ProductPicker"
import { api, ApiError, downloadFile } from "@/lib/api/client"
import type { Page, Sale, SaleCorrectionLink, SalesReport } from "@/lib/api/types"
import { currency } from "@/lib/format"
import { cn } from "@/lib/utils"

const ranges = ["Daily", "Weekly", "Monthly", "Custom"]
const PAGE_SIZE = 25

type Tab = "summary" | "journal"
type CashierOpt = { id: string; full_name: string }

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10)
}

function startOfWeek(d: Date) {
  const x = new Date(d)
  const day = x.getDay()
  const diff = day === 0 ? -6 : 1 - day
  x.setDate(x.getDate() + diff)
  return x
}

export default function ReportsPage() {
  const [tab, setTab] = useState<Tab>("summary")
  const [deepLinkSale, setDeepLinkSale] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get("tab") === "journal" || params.get("sale")) setTab("journal")
    setDeepLinkSale(params.get("sale"))
  }, [])

  return (
    <>
      <AppTopbar title="Reports" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        <div className="flex items-center rounded-lg border border-border bg-card p-0.5 w-fit">
          <button type="button" onClick={() => setTab("summary")} className={cn("rounded-md px-3.5 py-1.5 text-sm font-medium", tab === "summary" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>Summary</button>
          <button type="button" onClick={() => setTab("journal")} className={cn("rounded-md px-3.5 py-1.5 text-sm font-medium", tab === "journal" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>Sales Journal</button>
        </div>
        {tab === "summary" ? <SummaryTab /> : <SalesJournal initialSaleId={deepLinkSale} />}
      </div>
    </>
  )
}

function SummaryTab() {
  const [range, setRange] = useState("Weekly")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [data, setData] = useState<SalesReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams()
    if (range === "Custom") {
      if (!start || !end) return
      params.set("start", start)
      params.set("end", end)
    } else {
      params.set("range", range.toLowerCase())
    }
    api<SalesReport>(`/reports/sales?${params}`)
      .then((report) => { setData(report); setError(null) })
      .catch((err) => { setData(null); setError(err.message) })
  }, [range, start, end])

  const kpis = [
    { label: "Revenue", value: currency(data?.revenue ?? 0), icon: DollarSign },
    { label: "Gross profit", value: currency(data?.gross_profit ?? 0), icon: Percent },
    { label: "Transactions", value: String(data?.transactions ?? 0), icon: Wallet },
    { label: "Units sold", value: String(data?.units_sold ?? 0), icon: Package },
  ]

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center rounded-lg border border-border bg-card p-0.5">
          {ranges.map((r) => (
            <button key={r} type="button" onClick={() => setRange(r)} className={cn("rounded-md px-3.5 py-1.5 text-sm font-medium", range === r ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>{r}</button>
          ))}
        </div>
        {range === "Custom" && (
          <div className="flex items-center gap-2">
            <input type="date" min="2000-01-01" max="2099-12-31" value={start} onChange={(e) => setStart(e.target.value)} className="h-9 rounded-lg border border-border bg-card px-3 text-sm" />
            <input type="date" min="2000-01-01" max="2099-12-31" value={end} onChange={(e) => setEnd(e.target.value)} className="h-9 rounded-lg border border-border bg-card px-3 text-sm" />
          </div>
        )}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5">
        <div className="flex items-center gap-2 text-primary">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/15"><Sparkles className="size-4" /></span>
          <p className="text-sm font-semibold">Summary · {range}</p>
          <Badge variant="success" className="ml-auto">From live sales</Badge>
        </div>
        <p className="mt-3 text-sm leading-relaxed">
          Revenue is {currency(data?.revenue ?? 0)} across {data?.transactions ?? 0} transactions
          (average ticket {currency(data?.average_ticket ?? 0)}). Gross profit {currency(data?.gross_profit ?? 0)} uses current catalog cost (not historical batch cost).
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-2xl border border-border bg-card p-4">
            <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"><k.icon className="size-4" /></span>
            <p className="mt-3 text-2xl font-semibold tracking-tight">{k.value}</p>
            <p className="text-sm text-muted-foreground">{k.label}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-border bg-card p-5 lg:col-span-2">
          <h3 className="text-sm font-semibold">Revenue trend</h3>
          {data?.trend?.length ? <BarChart data={data.trend} className="mt-6 h-52" currencyFormat /> : <p className="mt-10 text-sm text-muted-foreground">No sales in this range.</p>}
        </div>
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold">Sales by category</h3>
          <div className="mt-6 flex justify-center">
            {data?.category_mix?.length ? <DonutChart data={data.category_mix} /> : <p className="text-sm text-muted-foreground">No sales in this range</p>}
          </div>
        </div>
      </div>
      <div className="rounded-2xl border border-border bg-card p-5">
        <h3 className="text-sm font-semibold">Top selling medicines</h3>
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="pb-2 font-medium">Medicine</th>
              <th className="pb-2 text-right font-medium">Units</th>
              <th className="pb-2 text-right font-medium">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {(data?.top_selling ?? []).map((t) => (
              <tr key={t.name} className="border-b border-border last:border-0">
                <td className="py-3 font-medium">{t.name}</td>
                <td className="py-3 text-right tabular-nums">{t.units}</td>
                <td className="py-3 text-right tabular-nums">{currency(t.revenue)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function SalesJournal({ initialSaleId }: { initialSaleId?: string | null }) {
  const today = useMemo(() => new Date(), [])
  const [product, setProduct] = useState<{ id: string; name: string; sku?: string } | null>(null)
  const [preset, setPreset] = useState("this_month")
  const [dateFrom, setDateFrom] = useState(isoDate(new Date(today.getFullYear(), today.getMonth(), 1)))
  const [dateTo, setDateTo] = useState(isoDate(today))
  const [q, setQ] = useState("")
  const [qLive, setQLive] = useState("")
  const [cashierId, setCashierId] = useState("")
  const [payment, setPayment] = useState("")
  const [status, setStatus] = useState("")
  const [correction, setCorrection] = useState("")
  const [cashiers, setCashiers] = useState<CashierOpt[]>([])
  const [page, setPage] = useState(0)
  const [data, setData] = useState<Page<Sale> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Sale | null>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    api<CashierOpt[]>("/sales/cashiers").then(setCashiers).catch(() => setCashiers([]))
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setQLive(q), 250)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    const now = new Date()
    if (preset === "today") {
      setDateFrom(isoDate(now)); setDateTo(isoDate(now))
    } else if (preset === "yesterday") {
      const y = new Date(now); y.setDate(y.getDate() - 1)
      setDateFrom(isoDate(y)); setDateTo(isoDate(y))
    } else if (preset === "this_week") {
      setDateFrom(isoDate(startOfWeek(now))); setDateTo(isoDate(now))
    } else if (preset === "this_month") {
      setDateFrom(isoDate(new Date(now.getFullYear(), now.getMonth(), 1))); setDateTo(isoDate(now))
    }
  }, [preset])

  const queryString = useMemo(() => {
    const params = new URLSearchParams()
    params.set("limit", String(PAGE_SIZE))
    params.set("offset", String(page * PAGE_SIZE))
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    if (qLive.trim()) params.set("q", qLive.trim())
    if (cashierId) params.set("cashier_id", cashierId)
    if (payment) params.set("payment_method", payment)
    if (status) params.set("status", status)
    if (correction) params.set("correction", correction)
    if (product) params.set("product_id", product.id)
    return params.toString()
  }, [page, dateFrom, dateTo, qLive, cashierId, payment, status, correction, product])

  useEffect(() => {
    setPage(0)
  }, [dateFrom, dateTo, qLive, cashierId, payment, status, correction, product])

  useEffect(() => {
    api<Page<Sale>>(`/sales?${queryString}`)
      .then((res) => { setData(res); setError(null) })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load journal"))
  }, [queryString])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const openSale = async (id: string) => {
    try {
      setSelected(await api<Sale>(`/sales/${id}`))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load sale")
    }
  }

  useEffect(() => {
    if (initialSaleId) void openSale(initialSaleId)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open deep-linked sale once
  }, [initialSaleId])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2 rounded-2xl border border-border bg-card p-4">
        <label className="text-xs text-muted-foreground">
          Period
          <select value={preset} onChange={(e) => setPreset(e.target.value)} className="mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground">
            <option value="today">Today</option>
            <option value="yesterday">Yesterday</option>
            <option value="this_week">This week</option>
            <option value="this_month">This month</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">
          From
          <input type="date" value={dateFrom} onChange={(e) => { setPreset("custom"); setDateFrom(e.target.value) }} className="mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground" />
        </label>
        <label className="text-xs text-muted-foreground">
          To
          <input type="date" value={dateTo} onChange={(e) => { setPreset("custom"); setDateTo(e.target.value) }} className="mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground" />
        </label>
        <label className="min-w-48 flex-1 text-xs text-muted-foreground">
          Search
          <div className="mt-1 flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-2">
            <Search className="size-3.5 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Sale #, product, SKU" className="h-full flex-1 bg-transparent text-sm text-foreground outline-none" />
          </div>
        </label>
        <label className="text-xs text-muted-foreground">
          Cashier
          <select value={cashierId} onChange={(e) => setCashierId(e.target.value)} className="mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground">
            <option value="">All</option>
            {cashiers.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted-foreground">
          Payment
          <select value={payment} onChange={(e) => setPayment(e.target.value)} className="mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground">
            <option value="">All</option>
            <option value="CASH">Cash</option>
            <option value="CARD">Card</option>
            <option value="MOBILE_MONEY">Mobile money</option>
            <option value="OTHER">Other</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground">
            <option value="">All</option>
            <option value="COMPLETED">Completed</option>
            <option value="PARTIALLY_REFUNDED">Partially refunded</option>
            <option value="REFUNDED">Refunded</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">
          Correction
          <select value={correction} onChange={(e) => setCorrection(e.target.value)} className="mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground">
            <option value="">All</option>
            <option value="normal">Normal</option>
            <option value="pending">Correction pending</option>
            <option value="corrected">Corrected originals (approved)</option>
            <option value="rejected">Correction rejected</option>
            <option value="correction_sale">Correction sales</option>
            <option value="correction_related">Correction-related</option>
            <option value="refunded">Refunded</option>
          </select>
        </label>
        <label className="w-56 text-xs text-muted-foreground">
          Product
          <div className="mt-1">
            <ProductPicker
              value={product}
              onSelect={(p) => setProduct({ id: p.id, name: p.name, sku: p.sku })}
              onClear={() => setProduct(null)}
              placeholder="Any product"
              showStock={false}
            />
          </div>
        </label>
        <Button
          type="button"
          variant="outline"
          className="gap-1.5"
          disabled={exporting}
          onClick={async () => {
            setExporting(true)
            try {
              const params = new URLSearchParams(queryString)
              params.delete("limit")
              params.delete("offset")
              await downloadFile(`/sales/export.csv?${params}`, "sales-journal.csv")
            } catch (err) {
              setError(err instanceof ApiError ? err.message : "Export failed")
            } finally {
              setExporting(false)
            }
          }}
        >
          <Download className="size-4" /> {exporting ? "Exporting…" : "Export CSV"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Sale #</th>
              <th className="px-4 py-3 font-medium">Cashier</th>
              <th className="px-4 py-3 font-medium">Products</th>
              <th className="px-4 py-3 text-right font-medium">Qty</th>
              <th className="px-4 py-3 text-right font-medium">Total</th>
              <th className="px-4 py-3 font-medium">Pay</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {(data?.items ?? []).map((sale) => {
              const qty = sale.items.reduce((a, i) => a + i.quantity, 0)
              const names = sale.items.map((i) => i.product_name).filter(Boolean).slice(0, 2).join(", ")
              const more = sale.items.length > 2 ? ` +${sale.items.length - 2}` : ""
              return (
                <tr key={sale.id} className="cursor-pointer hover:bg-muted/30" onClick={() => openSale(sale.id)}>
                  <td className="px-4 py-3 whitespace-nowrap text-xs text-muted-foreground">{new Date(sale.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono text-xs">{sale.sale_number}</td>
                  <td className="px-4 py-3">{sale.cashier_name ?? "—"}</td>
                  <td className="px-4 py-3 max-w-48 truncate">{names || "—"}{more}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{qty}</td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium">{currency(Number(sale.total))}</td>
                  <td className="px-4 py-3 text-xs">{sale.payment_method.replace("_", " ")}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      <Badge variant={sale.status === "COMPLETED" ? "success" : sale.status === "REFUNDED" ? "neutral" : "warning"}>{sale.status.replaceAll("_", " ")}</Badge>
                      {sale.correction?.status === "APPROVED" && <Badge variant="warning">Corrected → {sale.correction.corrected_sale_number}</Badge>}
                      {sale.correction?.status === "PENDING" && <Badge variant="warning">Correction pending</Badge>}
                      {sale.is_correction_of && <Badge variant="neutral">From {sale.is_correction_of.original_sale_number}</Badge>}
                    </div>
                  </td>
                </tr>
              )
            })}
            {!data?.items.length && (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">No sales match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <p className="text-muted-foreground">{data?.total ?? 0} sale{(data?.total ?? 0) === 1 ? "" : "s"}</p>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="outline" disabled={page <= 0} onClick={() => setPage((p) => Math.max(0, p - 1))}><ChevronLeft className="size-4" /></Button>
          <span className="tabular-nums">Page {page + 1} / {totalPages}</span>
          <Button type="button" size="sm" variant="outline" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)}><ChevronRight className="size-4" /></Button>
        </div>
      </div>

      {selected && <SaleDetailDrawer sale={selected} onClose={() => setSelected(null)} onOpenSale={openSale} />}
    </div>
  )
}

function CorrectionPanel({
  link,
  role,
  onOpenSale,
}: {
  link: SaleCorrectionLink
  role: "original" | "corrected"
  onOpenSale: (id: string) => void
}) {
  const diff = link.financial_difference != null ? Number(link.financial_difference) : null
  const reviewedLabel = link.status === "REJECTED" ? "Rejected by" : "Approved by"
  return (
    <div className="rounded-xl border border-warning/40 bg-warning/10 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">
          {role === "original" ? "Correction request" : "This sale is a correction"} {link.reference ? `· ${link.reference}` : ""}
        </p>
        <Badge variant={link.status === "APPROVED" ? "success" : link.status === "PENDING" ? "warning" : "neutral"}>{link.status}</Badge>
      </div>
      <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5 text-xs">
        <dt className="text-muted-foreground">Requested by</dt>
        <dd>{link.requested_by_name ?? "—"}{link.requested_at ? ` · ${new Date(link.requested_at).toLocaleString()}` : ""}</dd>
        {link.reason && (<><dt className="text-muted-foreground">Reason</dt><dd>{link.reason}</dd></>)}
        {link.status !== "PENDING" && (
          <>
            <dt className="text-muted-foreground">{reviewedLabel}</dt>
            <dd>{link.reviewed_by_name ?? "—"}{link.reviewed_at ? ` · ${new Date(link.reviewed_at).toLocaleString()}` : ""}</dd>
          </>
        )}
        {link.review_note && (<><dt className="text-muted-foreground">{link.status === "REJECTED" ? "Rejection reason" : "Review note"}</dt><dd>{link.review_note}</dd></>)}
        {link.original_sale_id && (
          <>
            <dt className="text-muted-foreground">Original sale</dt>
            <dd>
              {role === "corrected" ? (
                <button type="button" className="font-mono text-primary hover:underline" onClick={() => onOpenSale(link.original_sale_id!)}>
                  {link.original_sale_number}
                </button>
              ) : (
                <span className="font-mono">{link.original_sale_number}</span>
              )}
            </dd>
          </>
        )}
        {link.corrected_sale_id && (
          <>
            <dt className="text-muted-foreground">Corrected sale</dt>
            <dd>
              {role === "original" ? (
                <button type="button" className="font-mono text-primary hover:underline" onClick={() => onOpenSale(link.corrected_sale_id!)}>
                  {link.corrected_sale_number}
                </button>
              ) : (
                <span className="font-mono">{link.corrected_sale_number}</span>
              )}
            </dd>
          </>
        )}
        {link.return_number && (<><dt className="text-muted-foreground">Refund</dt><dd>{link.return_number} · {currency(Number(link.refund_amount ?? 0))}</dd></>)}
        {diff != null && (
          <>
            <dt className="text-muted-foreground">Financial difference</dt>
            <dd className="font-medium">
              {currency(diff)} {diff > 0 ? "(collected from customer)" : diff < 0 ? "(owed to customer)" : ""}
            </dd>
          </>
        )}
      </dl>
    </div>
  )
}

function SaleDetailDrawer({ sale, onClose, onOpenSale }: { sale: Sale; onClose: () => void; onOpenSale: (id: string) => void }) {
  const discountFactor = 1 - Number(sale.discount_percent || 0) / 100
  return (
    <Overlay onClose={onClose}>
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border bg-card" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-border p-5">
          <div>
            <p className="font-mono text-xs text-muted-foreground">{sale.sale_number}</p>
            <h2 className="text-lg font-semibold">{currency(Number(sale.total))}</h2>
            <p className="text-sm text-muted-foreground">
              {new Date(sale.created_at).toLocaleString()} · Cashier {sale.cashier_name ?? "—"} · {sale.payment_method.replace("_", " ")}
            </p>
            <p className="text-sm text-muted-foreground">Customer: {sale.customer_name || "Walk-in"}</p>
          </div>
          <Button type="button" variant="ghost" onClick={onClose}>Close</Button>
        </div>
        <div className="space-y-4 overflow-y-auto p-5 text-sm">
          <div className="grid grid-cols-2 gap-2 rounded-xl border border-border p-3">
            <div><p className="text-xs text-muted-foreground">Status</p><p className="font-medium">{sale.status}</p></div>
            <div><p className="text-xs text-muted-foreground">Subtotal</p><p>{currency(Number(sale.subtotal))}</p></div>
            <div><p className="text-xs text-muted-foreground">Discount</p><p>{Number(sale.discount_percent)}% ({currency(Number(sale.discount_amount))})</p></div>
            <div><p className="text-xs text-muted-foreground">Tax</p><p>{Number(sale.tax_rate)}% ({currency(Number(sale.tax_amount))})</p></div>
          </div>

          {sale.correction && <CorrectionPanel link={sale.correction} role="original" onOpenSale={onOpenSale} />}
          {sale.is_correction_of && <CorrectionPanel link={sale.is_correction_of} role="corrected" onOpenSale={onOpenSale} />}

          <div>
            <h3 className="mb-2 font-semibold">Items</h3>
            <div className="space-y-2">
              {sale.items.map((item) => {
                const batchCost = item.batch_cost_price != null ? Number(item.batch_cost_price) : null
                const lineDiscount = Number(item.line_total) * (1 - discountFactor)
                const netLine = Number(item.line_total) - lineDiscount
                const estProfit = batchCost != null ? netLine - item.quantity * batchCost : null
                return (
                  <div key={item.id} className="rounded-xl border border-border p-3">
                    <div className="flex justify-between gap-3">
                      <div>
                        <p className="font-medium">{item.product_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {item.product_sku ? `SKU ${item.product_sku} · ` : ""}
                          {item.quantity} × {currency(Number(item.unit_price))}
                          {item.quantity_returned ? ` · returned ${item.quantity_returned}` : ""}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Batch {item.batch_number || "—"}
                          {item.batch_expiry ? ` · exp ${item.batch_expiry}` : ""}
                          {batchCost != null ? ` · batch cost ${currency(batchCost)}` : ""}
                        </p>
                        {item.batch_id && (
                          <p className="text-xs text-muted-foreground">
                            Supplier: {item.batch_supplier_name || (item.batch_po_number ? "Unknown" : "Not recorded")}
                            {item.batch_po_number ? ` · PO ${item.batch_po_number}` : ""}
                          </p>
                        )}
                      </div>
                      <div className="text-right">
                        <p className="font-medium">{currency(Number(item.line_total))}</p>
                        {lineDiscount > 0 && <p className="text-xs text-muted-foreground">Discount -{currency(lineDiscount)}</p>}
                        {estProfit != null && <p className="text-xs text-muted-foreground">Est. profit {currency(estProfit)}</p>}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Line discount is the sale-level discount ({Number(sale.discount_percent)}%) spread across lines. Est. profit = line total after discount, before tax,
              minus quantity × the cost recorded on the sold batch (not current catalog cost).
            </p>
          </div>

          {!!sale.returns?.length && (
            <div>
              <h3 className="mb-2 font-semibold">Returns</h3>
              <ul className="space-y-2">
                {sale.returns.map((r) => (
                  <li key={r.id} className="rounded-xl border border-border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium">{r.return_number} · refund {currency(Number(r.refund_amount))}</p>
                      <Badge variant={r.restock ? "success" : "neutral"}>{r.restock ? "Restocked" : "Not restocked"}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Completed · {new Date(r.created_at).toLocaleString()}
                      {r.processed_by_name ? ` · by ${r.processed_by_name}` : ""}
                    </p>
                    <p className="text-xs">Reason: {r.reason}</p>
                    {!!r.items?.length && (
                      <ul className="mt-1 text-xs text-muted-foreground">
                        {r.items.map((ri, idx) => (
                          <li key={`${ri.product_id}-${idx}`}>
                            Returned {ri.quantity} × {ri.product_name ?? "item"} @ {currency(Number(ri.unit_price))}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!!sale.stock_movements?.length && (
            <div>
              <h3 className="mb-2 font-semibold">Inventory impact</h3>
              <ul className="space-y-1.5">
                {sale.stock_movements.map((m) => (
                  <li key={m.id} className="flex justify-between gap-3 rounded-lg border border-border px-3 py-2 text-xs">
                    <span>
                      {m.movement_type} · {m.product_name}
                      {m.batch_number ? ` · batch ${m.batch_number}` : ""}
                    </span>
                    <span className="tabular-nums font-medium">{m.quantity > 0 ? `+${m.quantity}` : m.quantity}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Overlay>
  )
}
