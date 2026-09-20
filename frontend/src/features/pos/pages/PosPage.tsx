"use client"

import { useEffect, useMemo, useState } from "react"
import { Search, ScanLine, Plus, Minus, Trash2, User, Banknote, Smartphone, CreditCard, Receipt, CheckCircle2, RotateCcw } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { api, ApiError } from "@/lib/api/client"
import { asMedicine, type Medicine } from "@/lib/api/map"
import type { Page, Product, Sale, Settings } from "@/lib/api/types"
import { currency } from "@/lib/format"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { notifyInventoryChanged } from "@/lib/inventory-sync"

type CartLine = { med: Medicine; qty: number }
type Pay = "CASH" | "MOBILE_MONEY" | "CARD"
const CART_KEY = "aq.pos.cart"

export default function POSPage() {
  const { can } = useAuth()
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<Medicine[]>([])
  const [cart, setCart] = useState<CartLine[]>([])
  const [discount, setDiscount] = useState(0)
  const [tax, setTax] = useState<number | null>(null)
  const [pay, setPay] = useState<Pay>("CASH")
  const [tendered, setTendered] = useState("")
  const [customer, setCustomer] = useState("")
  const [done, setDone] = useState<Sale | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [idem, setIdem] = useState(() => crypto.randomUUID())
  const [lookup, setLookup] = useState("")
  const [refundSale, setRefundSale] = useState<Sale | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)

  useEffect(() => {
    try {
      const raw = localStorage.getItem(CART_KEY)
      if (raw) setCart(JSON.parse(raw))
    } catch { /* ignore */ }
    api<Settings>("/settings").then(setSettings).catch(() => setSettings(null))
  }, [])
  useEffect(() => {
    localStorage.setItem(CART_KEY, JSON.stringify(cart))
  }, [cart])

  useEffect(() => {
    const t = setTimeout(() => {
      api<Page<Product>>(`/products?q=${encodeURIComponent(query)}&limit=12`)
        .then((p) => setResults(p.items.map(asMedicine)))
        .catch(() => setResults([]))
    }, 200)
    return () => clearTimeout(t)
  }, [query])

  const add = (m: Medicine) => {
    setError(null)
    setCart((c) => {
      const found = c.find((l) => l.med.id === m.id)
      const nextQty = found ? found.qty + 1 : 1
      if (nextQty > m.quantity) {
        setError(`${m.name} only has ${m.quantity} units on hand`)
        return c
      }
      if (found) return c.map((l) => (l.med.id === m.id ? { ...l, qty: nextQty } : l))
      return [...c, { med: m, qty: 1 }]
    })
  }
  const setQty = (id: string, delta: number) => setCart((c) => c.map((l) => {
    if (l.med.id !== id) return l
    const next = Math.max(1, Math.min(l.med.quantity, l.qty + delta))
    return { ...l, qty: next }
  }))
  const remove = (id: string) => setCart((c) => c.filter((l) => l.med.id !== id))

  const settingsTax = Number(settings?.tax_rate ?? 5)
  const taxRate = tax ?? settingsTax
  const taxChoices = Array.from(new Set([0, settingsTax, 15])).sort((a, b) => a - b)
  const pharmacyName = settings?.pharmacy_name || "AetherQore Pharmacy"
  const subtotal = cart.reduce((a, l) => a + l.med.price * l.qty, 0)
  const previewDiscount = subtotal * (discount / 100)
  const previewTax = (subtotal - previewDiscount) * (taxRate / 100)
  const previewTotal = subtotal - previewDiscount + previewTax
  const cashShort = pay === "CASH" && tendered !== "" && Number(tendered) < previewTotal

  const scan = async () => {
    if (!query) return
    try {
      const p = await api<Product>(`/products/barcode/${encodeURIComponent(query)}`)
      add(asMedicine(p))
      setQuery("")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Barcode not found")
    }
  }

  const charge = async () => {
    if (pay === "CASH" && Number(tendered || 0) < previewTotal) {
      setError("Cash tendered is less than the total")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const sale = await api<Sale>("/sales", {
        method: "POST",
        body: JSON.stringify({
          items: cart.map((l) => ({ product_id: l.med.id, quantity: l.qty })),
          payment_method: pay,
          amount_tendered: pay === "CASH" ? tendered || previewTotal : undefined,
          discount_percent: discount,
          tax_rate: taxRate,
          customer_name: customer || undefined,
          idempotency_key: idem,
        }),
      })
      const sold = cart
      setDone(sale)
      setCart([])
      localStorage.removeItem(CART_KEY)
      setIdem(crypto.randomUUID())
      setResults((current) => current.map((m) => {
        const line = sold.find((l) => l.med.id === m.id)
        return line ? { ...m, quantity: Math.max(0, m.quantity - line.qty) } : m
      }))
      notifyInventoryChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sale failed")
    } finally {
      setBusy(false)
    }
  }

  const findSale = async () => {
    try {
      const page = await api<Page<Sale>>(`/sales?q=${encodeURIComponent(lookup)}`)
      if (!page.items[0]) throw new ApiError(404, "NOT_FOUND", "Sale not found")
      setRefundSale(await api<Sale>(`/sales/${page.items[0].id}`))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sale not found")
    }
  }

  if (done) {
    return (
      <>
        <AppTopbar title="Point of Sale" />
        <div className="flex flex-1 items-center justify-center p-6">
          <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-8 text-center animate-fade-up">
            <span className="mx-auto flex size-16 items-center justify-center rounded-full bg-primary/10 text-primary"><CheckCircle2 className="size-8" /></span>
            <h2 className="mt-4 text-xl font-semibold">Payment complete</h2>
            <p className="mt-1 text-sm text-muted-foreground">{done.sale_number} · {currency(Number(done.total))} · {done.payment_method.replace("_", " ")}</p>
            {Number(done.change_due) > 0 && (
              <div className="mt-4 rounded-xl bg-muted p-3">
                <p className="text-xs text-muted-foreground">Change due</p>
                <p className="text-2xl font-semibold text-primary">{currency(Number(done.change_due))}</p>
              </div>
            )}
            <div className="mt-6 flex gap-2">
              <Button variant="outline" className="flex-1 gap-1.5" onClick={() => window.print()}><Receipt className="size-4" /> Print</Button>
              <Button className="flex-1" onClick={() => { setDone(null); setTendered(""); setDiscount(0); setTax(null); setCustomer("") }}>New sale</Button>
            </div>
            <div className="receipt mt-6 hidden print:block text-left text-xs">
              <p className="font-semibold">{pharmacyName}</p>
              <p>{done.sale_number}</p>
              {done.items.map((i) => (
                <p key={i.id}>{i.product_name} × {i.quantity} — {currency(Number(i.line_total))}</p>
              ))}
              <p className="mt-2 font-semibold">Total {currency(Number(done.total))}</p>
            </div>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <AppTopbar title="Point of Sale" />
      <div className="grid flex-1 gap-0 lg:grid-cols-[1fr_minmax(0,400px)]">
        <div className="flex flex-col p-4 md:p-6">
          <div className="flex gap-2.5">
            <div className="flex h-12 flex-1 items-center gap-2.5 rounded-xl border border-border bg-card px-4">
              <Search className="size-5 text-muted-foreground" />
              <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && scan()} placeholder="Search medicine or scan barcode…" className="h-full flex-1 bg-transparent text-base outline-none" />
            </div>
            <Button size="lg" variant="outline" className="h-12 gap-2 px-4" onClick={scan}><ScanLine className="size-5" /> Scan</Button>
          </div>
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          <div className="mt-4 grid flex-1 auto-rows-min grid-cols-2 gap-3 overflow-y-auto scrollbar-thin sm:grid-cols-3 xl:grid-cols-4">
            {results.map((m) => (
              <button key={m.id} onClick={() => add(m)} className="group flex flex-col items-start gap-1 rounded-xl border border-border bg-card p-3.5 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-sm">
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary"><Plus className="size-4" /></span>
                <p className="mt-1 line-clamp-2 text-sm font-medium leading-snug">{m.name}</p>
                <p className="text-xs text-muted-foreground">{m.brand}</p>
                <div className="mt-1 flex w-full items-center justify-between">
                  <span className="text-sm font-semibold">{currency(m.price)}</span>
                  <span className="text-[11px] text-muted-foreground">{Math.max(0, m.quantity - (cart.find((l) => l.med.id === m.id)?.qty ?? 0))} left</span>
                </div>
              </button>
            ))}
          </div>
          {can("sales.refund") && (
            <div className="mt-4 flex gap-2 rounded-xl border border-border bg-card p-3">
              <input value={lookup} onChange={(e) => setLookup(e.target.value)} placeholder="Find sale number to refund…" className="h-9 flex-1 rounded-lg border border-border px-3 text-sm outline-none" />
              <Button variant="outline" className="gap-1.5" onClick={findSale}><RotateCcw className="size-4" /> Refund</Button>
            </div>
          )}
        </div>

        <div className="flex flex-col border-t border-border bg-card lg:border-l lg:border-t-0">
          <div className="flex items-center gap-2 border-b border-border p-4">
            <User className="size-4 text-muted-foreground" />
            <input value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="Walk-in customer (optional)" className="flex-1 bg-transparent text-sm outline-none" />
            <Badge variant="neutral">{cart.reduce((a, l) => a + l.qty, 0)} items</Badge>
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin p-3">
            {cart.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-muted-foreground">
                <Receipt className="size-8" />
                <p className="text-sm">Cart is empty. Search or scan to add items.</p>
              </div>
            ) : (
              <ul className="space-y-2">
                {cart.map((l) => (
                  <li key={l.med.id} className="flex items-center gap-3 rounded-xl border border-border bg-background p-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{l.med.name}</p>
                      <p className="text-xs text-muted-foreground">{currency(l.med.price)} each · {l.med.quantity} in stock</p>
                    </div>
                    <div className="flex items-center gap-1 rounded-lg border border-border">
                      <button onClick={() => setQty(l.med.id, -1)} className="p-1.5 text-muted-foreground hover:text-foreground"><Minus className="size-3.5" /></button>
                      <span className="w-6 text-center text-sm font-medium tabular-nums">{l.qty}</span>
                      <button onClick={() => setQty(l.med.id, 1)} className="p-1.5 text-muted-foreground hover:text-foreground"><Plus className="size-3.5" /></button>
                    </div>
                    <span className="w-16 text-right text-sm font-semibold tabular-nums">{currency(l.med.price * l.qty)}</span>
                    <button onClick={() => remove(l.med.id)} className="text-muted-foreground hover:text-destructive"><Trash2 className="size-4" /></button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="border-t border-border p-4">
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between"><span className="text-muted-foreground">Subtotal (est.)</span><span>{currency(subtotal)}</span></div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-muted-foreground">
                  Discount
                  <span className="flex items-center rounded-md border border-border">
                    {[0, 5, 10].map((d) => (
                      <button key={d} onClick={() => setDiscount(d)} className={cn("px-2 py-0.5 text-xs", discount === d ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>{d}%</button>
                    ))}
                  </span>
                </span>
                <span className="text-destructive">-{currency(previewDiscount)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-muted-foreground">
                  Tax
                  <span className="flex items-center rounded-md border border-border">
                    {taxChoices.map((rate) => (
                      <button key={rate} type="button" onClick={() => setTax(rate)} className={cn("px-2 py-0.5 text-xs", taxRate === rate ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>{rate}%</button>
                    ))}
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="0.5"
                    value={taxRate}
                    onChange={(e) => setTax(Math.min(100, Math.max(0, Number(e.target.value) || 0)))}
                    className="h-6 w-14 rounded-md border border-border bg-background px-1.5 text-right text-xs outline-none"
                    aria-label="Tax percent"
                  />
                </span>
                <span>{currency(previewTax)}</span>
              </div>
              <div className="flex items-center justify-between border-t border-border pt-2 text-base font-semibold">
                <span>Total (est.)</span>
                <span className="tabular-nums">{currency(previewTotal)}</span>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {([
                { k: "CASH" as const, label: "Cash", icon: Banknote },
                { k: "MOBILE_MONEY" as const, label: "Mobile", icon: Smartphone },
                { k: "CARD" as const, label: "Card", icon: CreditCard },
              ]).map((p) => (
                <button key={p.k} onClick={() => setPay(p.k)} className={cn("flex flex-col items-center gap-1 rounded-xl border py-2.5 text-xs font-medium", pay === p.k ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted")}>
                  <p.icon className="size-5" /> {p.label}
                </button>
              ))}
            </div>
            {pay === "CASH" && (
              <div className="mt-3 flex items-center gap-3">
                <div className="flex h-10 flex-1 items-center gap-2 rounded-lg border border-border bg-background px-3">
                  <span className="text-sm text-muted-foreground">Tendered</span>
                  <input value={tendered} onChange={(e) => setTendered(e.target.value)} inputMode="decimal" placeholder="0.00" className="h-full flex-1 bg-transparent text-right text-sm outline-none" />
                </div>
              </div>
            )}
            {cashShort && <p className="mt-2 text-sm text-destructive">Tendered amount is short of the total.</p>}
            <Button size="lg" className="mt-3 h-12 w-full text-base" disabled={cart.length === 0 || busy || cashShort} onClick={charge}>
              {busy ? "Charging…" : `Charge ${currency(previewTotal)}`}
            </Button>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">Totals are calculated on the server. Cart survives refresh.</p>
          </div>
        </div>
      </div>
      {refundSale && <RefundDialog sale={refundSale} onClose={() => setRefundSale(null)} />}
    </>
  )
}

function RefundDialog({ sale, onClose }: { sale: Sale; onClose: () => void }) {
  const [qty, setQty] = useState<Record<string, number>>({})
  const [reason, setReason] = useState("Customer return")
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    const items = sale.items.filter((i) => (qty[i.id] || 0) > 0).map((i) => ({ sale_item_id: i.id, quantity: qty[i.id] }))
    if (!items.length) {
      setError("Enter a return quantity")
      return
    }
    setBusy(true)
    try {
      const result = await api<{ return_number: string; refund_amount: number }>("/returns", { method: "POST", body: JSON.stringify({ sale_id: sale.id, reason, restock: true, items }) })
      setDone(`${result.return_number} refunded ${currency(Number(result.refund_amount))}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Return failed")
    } finally {
      setBusy(false)
    }
  }
  return (
    <Overlay onClose={onClose}>
      <div className="w-full max-w-lg space-y-3 rounded-2xl border border-border bg-card p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">Refund {sale.sale_number}</h2>
        {sale.items.map((i) => (
          <div key={i.id} className="flex items-center justify-between text-sm">
            <span>{i.product_name} · returnable {i.returnable}</span>
            <input type="number" min={0} max={i.returnable} value={qty[i.id] ?? 0} onChange={(e) => setQty((q) => ({ ...q, [i.id]: Number(e.target.value) }))} className="h-8 w-16 rounded border border-border px-2" />
          </div>
        ))}
        <input value={reason} onChange={(e) => setReason(e.target.value)} className="h-9 w-full rounded-lg border border-border px-3 text-sm" />
        {error && <p className="text-sm text-destructive">{error}</p>}
        {done && <p className="text-sm text-primary">{done}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{done ? "Close" : "Cancel"}</Button>
          <Button onClick={submit} disabled={busy || !!done}>{busy ? "Processing…" : "Process refund"}</Button>
        </div>
      </div>
    </Overlay>
  )
}
