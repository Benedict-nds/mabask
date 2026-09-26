"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, Check, PackageCheck, Percent, Plus, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ProductPicker } from "@/features/inventory/components/ProductPicker"
import { api, ApiError } from "@/lib/api/client"
import type { DiscountMode, ExtractResult, InvoiceImportResult, Product, Supplier } from "@/lib/api/types"
import { currency, normalizeExpiryInput } from "@/lib/format"
import { cn } from "@/lib/utils"

type Picked = { id: string; name: string; sku?: string; cost: number | null; selling: number | null }

type ReviewLine = {
  key: string
  row: number | null
  description: string
  product: Picked | null
  confidence: number
  createNew: boolean
  newName: string
  reorder: string
  quantity: string
  rate: string
  discount: string
  amount: string
  selling: string
  batch: string
  expiry: string
  hints: string[]
  archived: { id: string; name: string } | null
}

type PriceSource = "explicit" | "markup" | "kept"

const FIELD_LABELS: Record<string, string> = {
  name: "Description",
  quantity: "Quantity",
  rate: "Rate (unit cost)",
  discount: "Discount",
  amount: "Amount / Extended",
  expiry: "Expiry",
  batch: "Batch",
  selling_price: "Selling price",
}

const round2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100
const num = (v: string) => (v.trim() === "" ? NaN : Number(v))
const toStr = (v: number | string | null | undefined) => (v === null || v === undefined ? "" : String(Number(v)))

export function markupPrice(cost: number, markupPercent: number) {
  return round2(cost * (1 + markupPercent / 100))
}

function lineAmounts(qty: number, rate: number, discount: number, mode: DiscountMode) {
  const gross = round2(qty * rate)
  const discountAmount = mode === "percent" ? round2((gross * discount) / 100) : round2(discount)
  return { gross, discountAmount, net: round2(gross - discountAmount) }
}

const tolerance = (qty: number) => 0.01 + qty * 0.005 + 1e-9

function initialLines(result: ExtractResult, canCreate: boolean): ReviewLine[] {
  return result.items.map((item) => {
    const archived = item.archived_product_id ? { id: item.archived_product_id, name: item.archived_product_name ?? item.name } : null
    const description = item.description || item.name
    const readable = (item.issues ?? []).filter((i) => i.startsWith("Could not read expiry"))
    return {
      key: crypto.randomUUID(),
      row: item.row ?? null,
      description,
      product: item.matched && item.product_id
        ? {
            id: item.product_id,
            name: item.name,
            sku: item.product_sku,
            cost: item.current_cost_price == null ? null : Number(item.current_cost_price),
            selling: item.current_selling_price == null ? null : Number(item.current_selling_price),
          }
        : null,
      confidence: item.confidence,
      createNew: !item.matched && !archived && canCreate,
      newName: description,
      reorder: "0",
      quantity: item.quantity ? String(item.quantity) : "",
      rate: toStr(item.unit_cost),
      discount: item.discount && Number(item.discount) !== 0 ? toStr(item.discount) : "",
      amount: toStr(item.amount),
      selling: toStr(item.selling_price),
      batch: item.batch ?? "",
      expiry: item.expiry ?? "",
      hints: readable,
      archived,
    }
  })
}

export function InvoiceReview({
  result,
  canCreate,
  canUpdatePrices,
  canSaveDefault,
  onDone,
  onCancel,
}: {
  result: ExtractResult
  canCreate: boolean
  canUpdatePrices: boolean
  canSaveDefault: boolean
  onDone: (res: InvoiceImportResult) => void
  onCancel: () => void
}) {
  const defaultMarkup = result.default_markup_percent == null ? "" : String(Number(result.default_markup_percent))
  const [lines, setLines] = useState<ReviewLine[]>(() => initialLines(result, canCreate))
  const [markup, setMarkup] = useState(defaultMarkup)
  const [discountMode, setDiscountMode] = useState<DiscountMode>(result.discount_mode)
  const [updateExisting, setUpdateExisting] = useState(false)
  const [rememberDefault, setRememberDefault] = useState(false)
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [supplierId, setSupplierId] = useState(result.supplier_id ?? "")
  const [notes, setNotes] = useState("")
  const [batchFill, setBatchFill] = useState("")
  const [showErrors, setShowErrors] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<Supplier[]>("/suppliers").then(setSuppliers).catch(() => setSuppliers([]))
  }, [])

  const markupValue = num(markup)
  const markupValid = !Number.isNaN(markupValue) && markupValue >= 0 && markupValue <= 1000
  const hasDiscountColumn = Boolean(result.columns.discount) || lines.some((l) => l.discount !== "")

  const computed = useMemo(
    () =>
      lines.map((line) => {
        const qty = num(line.quantity)
        const rate = num(line.rate)
        const discount = line.discount.trim() === "" ? 0 : Number(line.discount)
        const { gross, discountAmount, net } = lineAmounts(qty || 0, rate || 0, discount || 0, discountMode)
        const invoiceAmount = line.amount.trim() === "" ? null : Number(line.amount)
        const mismatch = invoiceAmount !== null && !Number.isNaN(invoiceAmount) && Math.abs(invoiceAmount - net) > tolerance(qty || 0)
        let hint: string | null = null
        if (mismatch && discount > 0) {
          const other: DiscountMode = discountMode === "percent" ? "amount" : "percent"
          const alt = lineAmounts(qty || 0, rate || 0, discount, other)
          if (Math.abs((invoiceAmount ?? 0) - alt.net) <= tolerance(qty || 0)) {
            hint = `It matches if Discount is read as ${other === "percent" ? "a percentage" : "a GH₵ amount"}; switch the discount setting above.`
          }
        }
        const suggested = markupValid && !Number.isNaN(rate) ? markupPrice(rate, markupValue) : null
        const source: PriceSource = line.selling.trim() !== "" ? "explicit" : line.createNew || updateExisting ? "markup" : "kept"
        const finalPrice =
          source === "explicit" ? Number(line.selling) : source === "markup" ? suggested : line.product?.selling ?? null

        const errors: string[] = []
        if (!line.product && !line.createNew) {
          errors.push(
            line.archived
              ? `Matches archived medicine “${line.archived.name}”. Restore it in Inventory, or pick another medicine.`
              : canCreate
                ? "Choose an existing medicine or create it as new"
                : "Not in inventory. Ask someone with inventory access to add it.",
          )
        }
        if (line.createNew && !line.newName.trim()) errors.push("Enter the medicine name")
        if (line.createNew && (!Number.isInteger(num(line.reorder)) || num(line.reorder) < 0)) errors.push("Reorder point must be 0 or more")
        if (!Number.isInteger(qty) || qty <= 0) errors.push("Quantity must be a whole number above 0")
        if (Number.isNaN(rate) || rate < 0) errors.push("Enter the rate (unit cost)")
        if (Number.isNaN(discount) || discount < 0) errors.push("Discount must be 0 or more")
        else if (discountMode === "percent" && discount > 100) errors.push("Discount cannot exceed 100%")
        else if (discountMode === "amount" && discountAmount > gross) errors.push("Discount is larger than the line")
        if (invoiceAmount !== null && Number.isNaN(invoiceAmount)) errors.push("Amount is not a number")
        if (mismatch) errors.push(`Invoice amount ${currency(invoiceAmount ?? 0)} ≠ calculated ${currency(net)}${hint ? `. ${hint}` : ""}`)
        if (line.selling.trim() !== "" && (Number.isNaN(Number(line.selling)) || Number(line.selling) < 0)) errors.push("Selling price must be 0 or more")
        if (source === "markup" && suggested === null) errors.push("Enter a markup % (or type a selling price for this line)")
        if (!line.batch.trim()) errors.push("Batch number is required to receive stock")
        if (!line.expiry) errors.push("Expiry date is required to receive stock")
        return { qty, rate, gross, discountAmount, net, invoiceAmount, mismatch, suggested, source, finalPrice, errors }
      }),
    [lines, discountMode, markupValid, markupValue, updateExisting, canCreate],
  )

  const errorCount = computed.filter((c) => c.errors.length).length
  const invoiceTotal = computed.reduce((sum, c) => sum + (Number.isNaN(c.net) ? 0 : c.net), 0)
  const units = computed.reduce((sum, c) => sum + (Number.isInteger(c.qty) && c.qty > 0 ? c.qty : 0), 0)
  const newCount = new Set(lines.filter((l) => l.createNew).map((l) => l.newName.trim().toLowerCase())).size
  const priceChanges = lines.filter((l, i) => l.product && computed[i].source !== "kept" && computed[i].finalPrice !== l.product.selling).length
  const example = computed.find((c, i) => !Number.isNaN(c.rate) && c.rate > 0 && lines[i])
  const blankBatches = lines.filter((l) => !l.batch.trim()).length

  const update = (key: string, patch: Partial<ReviewLine>) => setLines((current) => current.map((l) => (l.key === key ? { ...l, ...patch } : l)))

  const pick = (key: string, product: Product) =>
    update(key, {
      product: { id: product.id, name: product.name, sku: product.sku, cost: Number(product.cost_price), selling: Number(product.selling_price) },
      createNew: false,
      archived: null,
    })

  const submit = async () => {
    setShowErrors(true)
    if (!lines.length) {
      setError("There are no lines to receive")
      return
    }
    if (errorCount) {
      setError(`Fix the ${errorCount} highlighted line${errorCount === 1 ? "" : "s"}. Nothing has been received yet.`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const res = await api<InvoiceImportResult>("/receiving/invoice", {
        method: "POST",
        body: JSON.stringify({
          supplier_id: supplierId || null,
          notes: notes.trim(),
          source: result.source === "ai" ? "AI invoice" : "CSV invoice",
          markup_percent: markup.trim() === "" ? null : markup.trim(),
          discount_mode: discountMode,
          update_existing_prices: updateExisting,
          items: lines.map((line) => ({
            row: line.row,
            description: line.description.slice(0, 300),
            product_id: line.createNew ? null : line.product?.id ?? null,
            new_product: line.createNew ? { name: line.newName.trim(), reorder_threshold: Number(line.reorder || 0) } : null,
            quantity: Number(line.quantity),
            rate: line.rate.trim(),
            discount: line.discount.trim() || "0",
            amount: line.amount.trim() === "" ? null : line.amount.trim(),
            selling_price: line.selling.trim() === "" ? null : line.selling.trim(),
            batch_number: line.batch.trim(),
            expiry_date: normalizeExpiryInput(line.expiry),
          })),
        }),
      })
      if (rememberDefault && markupValid) {
        await api("/settings", { method: "PATCH", body: JSON.stringify({ default_markup_percent: markup.trim() }) }).catch(() => undefined)
      }
      onDone(res)
    } catch (err) {
      setError(`${err instanceof ApiError ? err.message : "Import failed"}. Nothing was received.`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="space-y-3 rounded-2xl border border-primary/30 bg-primary/5 p-4">
          <div className="flex items-center gap-2">
            <Percent className="size-4 text-primary" />
            <p className="text-sm font-semibold">Selling price markup (applies to this whole import)</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Markup
              <span className="flex items-center gap-1">
                <input
                  value={markup}
                  onChange={(e) => setMarkup(e.target.value)}
                  inputMode="decimal"
                  placeholder="e.g. 30"
                  aria-label="Markup percent"
                  className="h-10 w-24 rounded-lg border border-border bg-card px-3 text-right text-base font-semibold tabular-nums"
                />
                <span className="text-base font-semibold">%</span>
              </span>
            </label>
            {example && markupValid ? (
              <div className="text-sm leading-6 tabular-nums">
                <p>Cost: {currency(example.rate)}</p>
                <p>Markup: {currency(round2((example.rate * markupValue) / 100))}</p>
                <p className="font-semibold">Selling: {currency(markupPrice(example.rate, markupValue))}</p>
              </div>
            ) : (
              <p className="max-w-xs text-sm text-muted-foreground">
                {defaultMarkup ? "Enter a valid percentage." : "No default markup is set yet. Enter the percentage to use for this invoice."}
              </p>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Selling price = cost × (1 + markup ÷ 100). A selling price typed on a line always wins over the markup.
            {defaultMarkup ? ` Pharmacy default: ${defaultMarkup}%.` : ""}
          </p>
          {canSaveDefault && markupValid && markup.trim() !== defaultMarkup && (
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={rememberDefault} onChange={(e) => setRememberDefault(e.target.checked)} />
              Save {markup.trim()}% as the pharmacy default for future imports
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm">
            Medicines already in inventory
            <select
              value={updateExisting ? "update" : "keep"}
              onChange={(e) => setUpdateExisting(e.target.value === "update")}
              disabled={!canUpdatePrices}
              className="h-9 rounded-lg border border-border bg-card px-2 text-sm"
            >
              <option value="keep">Keep their current selling price</option>
              <option value="update">Update selling price to cost + markup</option>
            </select>
          </label>
        </div>

        <div className="space-y-3 rounded-2xl border border-border bg-card p-4">
          <label className="flex flex-col gap-1 text-sm">
            Supplier (optional)
            <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className="h-9 rounded-lg border border-border px-2 text-sm">
              <option value="">Not recorded (unknown supplier)</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground">
              {supplierId ? "An approved purchase order is created so batches trace to this supplier." : "No purchase order is created; batch supplier shows “Not recorded”."}
            </span>
          </label>
          {hasDiscountColumn && (
            <div className="text-sm">
              <p>Discount column means</p>
              <div className="mt-1 flex gap-2">
                {(["percent", "amount"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setDiscountMode(mode)}
                    className={cn(
                      "rounded-lg border px-3 py-1.5 text-xs font-medium",
                      discountMode === mode ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground",
                    )}
                  >
                    {mode === "percent" ? "Percentage of the line (%)" : "Amount off the line (GH₵)"}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">Detected from {result.discount_mode_source}. Blank discount = 0.</p>
            </div>
          )}
          <label className="flex flex-col gap-1 text-sm">
            Notes (optional)
            <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} placeholder="e.g. Invoice 4471" className="h-9 rounded-lg border border-border px-3 text-sm" />
          </label>
          {blankBatches > 0 && (
            <div className="flex flex-wrap items-end gap-2 text-sm">
              <label className="flex flex-col gap-1">
                Fill {blankBatches} blank batch number{blankBatches === 1 ? "" : "s"} with
                <input value={batchFill} onChange={(e) => setBatchFill(e.target.value)} maxLength={64} placeholder="Batch / lot from the packs" className="h-9 rounded-lg border border-border px-3 text-sm" />
              </label>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!batchFill.trim()}
                onClick={() => setLines((current) => current.map((l) => (l.batch.trim() ? l : { ...l, batch: batchFill.trim() })))}
              >
                Apply
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-muted-foreground">{result.source === "ai" ? "Read by AI:" : "Columns recognised:"}</span>
        {Object.entries(result.columns).map(([field, header]) => (
          <Badge key={field} variant="neutral">
            {header} → {FIELD_LABELS[field] ?? field}
          </Badge>
        ))}
        {result.ignored_columns.length > 0 && <span className="text-muted-foreground">Ignored: {result.ignored_columns.join(", ")}</span>}
        {result.skipped_rows.length > 0 && (
          <span className="text-muted-foreground">
            · Skipped {result.skipped_rows.length} row{result.skipped_rows.length === 1 ? "" : "s"} without a quantity ({result.skipped_rows.map((r) => `row ${r.row}`).join(", ")})
          </span>
        )}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border bg-card scrollbar-thin">
        <table className="w-full min-w-[1180px] text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">Medicine</th>
              <th className="px-3 py-2 font-medium">Qty</th>
              <th className="px-3 py-2 font-medium">Cost (Rate)</th>
              <th className="px-3 py-2 font-medium">Discount{discountMode === "percent" ? " %" : " GH₵"}</th>
              <th className="px-3 py-2 font-medium">Amount</th>
              <th className="px-3 py-2 font-medium">Markup</th>
              <th className="px-3 py-2 font-medium">Selling price</th>
              <th className="px-3 py-2 font-medium">Batch</th>
              <th className="px-3 py-2 font-medium">Expiry</th>
              <th className="px-3 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {lines.map((line, index) => {
              const c = computed[index]
              const flagged = showErrors && c.errors.length > 0
              return (
                <LineRows
                  key={line.key}
                  index={index}
                  line={line}
                  c={c}
                  flagged={flagged}
                  markupLabel={markupValid ? `${markupValue}%` : "—"}
                  canCreate={canCreate}
                  onUpdate={(patch) => update(line.key, patch)}
                  onPick={(p) => pick(line.key, p)}
                  onRemove={() => setLines((current) => current.filter((l) => l.key !== line.key))}
                />
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4">
        <div className="text-sm tabular-nums">
          <p className="font-semibold">
            {lines.length} line{lines.length === 1 ? "" : "s"} · {units} units · Invoice total {currency(round2(invoiceTotal))}
          </p>
          <p className="text-xs text-muted-foreground">
            {newCount} new medicine{newCount === 1 ? "" : "s"} will be created at zero stock, then received · {priceChanges} existing selling price
            {priceChanges === 1 ? "" : "s"} will change
          </p>
        </div>
        {showErrors && errorCount > 0 && (
          <Badge variant="warning" className="gap-1">
            <AlertTriangle className="size-3" /> {errorCount} line{errorCount === 1 ? "" : "s"} need attention
          </Badge>
        )}
        {!showErrors && errorCount === 0 && lines.length > 0 && (
          <Badge variant="success" className="gap-1">
            <Check className="size-3" /> Ready to receive
          </Badge>
        )}
        <div className="ml-auto flex gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" className="gap-1.5" disabled={saving || !lines.length} onClick={submit}>
            <PackageCheck className="size-4" /> {saving ? "Receiving…" : `Confirm & receive ${lines.length} line${lines.length === 1 ? "" : "s"}`}
          </Button>
        </div>
        {error && <p className="w-full text-sm text-destructive">{error}</p>}
        <p className="w-full text-xs text-muted-foreground">
          All lines are checked together. If any line fails, nothing is received and no medicine is created.
        </p>
      </div>
    </div>
  )
}

function LineRows({
  index,
  line,
  c,
  flagged,
  markupLabel,
  canCreate,
  onUpdate,
  onPick,
  onRemove,
}: {
  index: number
  line: ReviewLine
  c: {
    net: number
    invoiceAmount: number | null
    mismatch: boolean
    suggested: number | null
    source: PriceSource
    finalPrice: number | null
    errors: string[]
  }
  flagged: boolean
  markupLabel: string
  canCreate: boolean
  onUpdate: (patch: Partial<ReviewLine>) => void
  onPick: (product: Product) => void
  onRemove: () => void
}) {
  const cellInput = "h-9 rounded-lg border border-border bg-background px-2 text-sm"
  const pricePlaceholder = c.source === "kept" ? toStr(line.product?.selling ?? null) : c.suggested === null ? "" : c.suggested.toFixed(2)
  return (
    <>
      <tr className={cn("align-top", flagged && "bg-destructive/5")}>
        <td className="px-3 py-2 text-xs text-muted-foreground">
          {index + 1}
          {line.row ? <span className="block">row {line.row}</span> : null}
        </td>
        <td className="px-2 py-2">
          <div className="w-64 space-y-1">
            {line.createNew ? (
              <>
                <div className="flex items-center gap-1.5">
                  <input value={line.newName} onChange={(e) => onUpdate({ newName: e.target.value })} maxLength={200} aria-label="New medicine name" className={cn(cellInput, "w-full")} />
                </div>
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <Badge variant="default" className="gap-1">
                    <Plus className="size-3" /> New medicine
                  </Badge>
                  <label className="flex items-center gap-1 text-muted-foreground">
                    Reorder at
                    <input value={line.reorder} onChange={(e) => onUpdate({ reorder: e.target.value })} type="number" min={0} step={1} className="h-7 w-16 rounded-md border border-border px-1.5 text-xs" aria-label="Reorder point" />
                  </label>
                  <button type="button" className="text-primary hover:underline" onClick={() => onUpdate({ createNew: false })}>
                    Pick existing
                  </button>
                </div>
              </>
            ) : (
              <>
                <ProductPicker
                  value={line.product}
                  onSelect={onPick}
                  onClear={() => onUpdate({ product: null })}
                  onCreateNew={canCreate ? (name) => onUpdate({ createNew: true, newName: name || line.description, product: null }) : undefined}
                  placeholder="Search medicine…"
                />
                {line.product && (
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <Badge variant={line.confidence >= 0.9 ? "success" : "warning"}>{line.confidence >= 0.9 ? "Matched" : "Check match"}</Badge>
                    {line.description && line.description !== line.product.name && <span className="truncate">Invoice: {line.description}</span>}
                  </div>
                )}
                {!line.product && canCreate && (
                  <button type="button" className="text-xs text-primary hover:underline" onClick={() => onUpdate({ createNew: true, newName: line.newName || line.description })}>
                    Create “{line.description || "new medicine"}” as new
                  </button>
                )}
              </>
            )}
          </div>
        </td>
        <td className="px-2 py-2">
          <input value={line.quantity} onChange={(e) => onUpdate({ quantity: e.target.value })} type="number" min={1} step={1} className={cn(cellInput, "w-20")} aria-label="Quantity" />
        </td>
        <td className="px-2 py-2">
          <input value={line.rate} onChange={(e) => onUpdate({ rate: e.target.value })} inputMode="decimal" className={cn(cellInput, "w-24")} aria-label="Rate (unit cost)" />
          {line.product?.cost != null && line.rate !== "" && Number(line.rate) !== line.product.cost && (
            <p className="mt-1 text-xs text-muted-foreground">was {currency(line.product.cost)}</p>
          )}
        </td>
        <td className="px-2 py-2">
          <input value={line.discount} onChange={(e) => onUpdate({ discount: e.target.value })} inputMode="decimal" placeholder="0" className={cn(cellInput, "w-20")} aria-label="Discount" />
        </td>
        <td className="px-2 py-2 tabular-nums">
          <p className={cn("font-medium", c.mismatch && "text-destructive")}>{currency(c.net)}</p>
          <p className="text-xs text-muted-foreground">
            {c.invoiceAmount === null ? "No invoice amount" : c.mismatch ? `Invoice ${currency(c.invoiceAmount)}` : "Matches invoice"}
          </p>
        </td>
        <td className="px-3 py-2 text-xs">
          {c.source === "explicit" ? <Badge variant="neutral">Typed price</Badge> : c.source === "markup" ? <span className="font-medium">{markupLabel}</span> : <span className="text-muted-foreground">Kept</span>}
        </td>
        <td className="px-2 py-2">
          <input
            value={line.selling}
            onChange={(e) => onUpdate({ selling: e.target.value })}
            inputMode="decimal"
            placeholder={pricePlaceholder}
            className={cn(cellInput, "w-24 placeholder:text-foreground/70")}
            aria-label="Selling price"
          />
          <p className="mt-1 text-xs text-muted-foreground tabular-nums">
            {c.source === "kept"
              ? line.product?.selling != null
                ? `Current price${c.suggested !== null ? ` · markup gives ${currency(c.suggested)}` : ""}`
                : ""
              : c.source === "markup"
                ? c.suggested !== null
                  ? "Suggested (cost + markup)"
                  : "Needs markup"
                : c.suggested !== null
                  ? `Markup would give ${currency(c.suggested)}`
                  : ""}
          </p>
        </td>
        <td className="px-2 py-2">
          <input value={line.batch} onChange={(e) => onUpdate({ batch: e.target.value })} maxLength={64} placeholder="Required" className={cn(cellInput, "w-28")} aria-label="Batch number" />
        </td>
        <td className="px-2 py-2">
          <input value={line.expiry} onChange={(e) => onUpdate({ expiry: e.target.value, hints: [] })} type="date" min="2000-01-01" max="2099-12-31" className={cellInput} aria-label="Expiry date" />
        </td>
        <td className="px-2 py-2">
          <button type="button" onClick={onRemove} className="flex h-9 items-center text-muted-foreground hover:text-destructive" aria-label="Remove line">
            <Trash2 className="size-4" />
          </button>
        </td>
      </tr>
      {(flagged || line.hints.length > 0) && (
        <tr className={flagged ? "bg-destructive/5" : ""}>
          <td />
          <td colSpan={10} className="px-2 pb-2 text-xs">
            {line.hints.map((h) => (
              <p key={h} className="text-warning">{h}</p>
            ))}
            {flagged && c.errors.map((e) => <p key={e} className="text-destructive">{e}</p>)}
          </td>
        </tr>
      )}
    </>
  )
}
