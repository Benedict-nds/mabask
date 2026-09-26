"use client"

import { useEffect, useState, type ComponentType } from "react"
import Link from "next/link"
import {
  UploadCloud,
  FileText,
  Sparkles,
  Check,
  ScanLine,
  Loader2,
  CircleCheck,
  ArrowRight,
  ClipboardList,
  Hand,
  FileSpreadsheet,
} from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button, ButtonLink } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { ProductPicker } from "@/features/inventory/components/ProductPicker"
import { QuickAddProduct } from "@/features/inventory/components/QuickAddProduct"
import { InvoiceReview } from "@/features/purchases/components/InvoiceReview"
import { api, ApiError } from "@/lib/api/client"
import type { ExtractResult, InvoiceImportResult, Product, PurchaseOrder, ReceiptResult, Supplier } from "@/lib/api/types"
import { currency, normalizeExpiryInput } from "@/lib/format"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"

type Method = "hub" | "ai" | "csv" | "manual"
type ManualMode = "choose" | "po" | "adhoc"
type Stage = "upload" | "processing" | "review" | "done"

const extractSteps = ["Upload invoice", "Extract lines", "Review & approve", "Imported"]

type AdhocLine = {
  key: string
  product: { id: string; name: string; sku: string } | null
  quantity: string
  batch_number: string
  expiry_date: string
  unit_cost: string
  notes: string
}

type ManualResult = {
  reference: string
  supplier: string | null
  poNumber: string | null
  units: number
  lines: number
}

function emptyAdhoc(): AdhocLine {
  return { key: crypto.randomUUID(), product: null, quantity: "1", batch_number: "", expiry_date: "", unit_cost: "", notes: "" }
}

export default function ReceivingPage() {
  const { can } = useAuth()
  const [method, setMethod] = useState<Method>("hub")
  const [manualMode, setManualMode] = useState<ManualMode>("choose")
  const [stage, setStage] = useState<Stage>("upload")
  const [extracted, setExtracted] = useState<ExtractResult | null>(null)
  const [fileName, setFileName] = useState("No file selected")
  const [error, setError] = useState<string | null>(null)
  const [imported, setImported] = useState<InvoiceImportResult | null>(null)
  const [manualResult, setManualResult] = useState<ManualResult | null>(null)
  const [accept, setAccept] = useState(".csv,text/csv,.txt,image/*,.pdf")

  const resetExtract = () => {
    setStage("upload")
    setExtracted(null)
    setImported(null)
    setFileName("No file selected")
    setError(null)
  }

  const goHub = () => {
    setMethod("hub")
    setManualMode("choose")
    setManualResult(null)
    resetExtract()
  }

  const startExtract = (next: "ai" | "csv") => {
    setMethod(next)
    setAccept(next === "csv" ? ".csv,text/csv,.txt" : "image/*,.pdf,.csv,text/csv,.txt")
    resetExtract()
  }

  const extract = async (file: File) => {
    setFileName(file.name)
    setStage("processing")
    setError(null)
    const fd = new FormData()
    fd.append("file", file)
    try {
      const res = await api<ExtractResult>("/receiving/extract", { method: "POST", body: fd })
      setExtracted(res)
      setStage("review")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not read invoice")
      setStage("upload")
    }
  }

  const stageIndex = stage === "upload" ? 0 : stage === "processing" ? 1 : stage === "review" ? 2 : 3

  return (
    <>
      <AppTopbar title="Receive Shipment" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        {method !== "hub" && (
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={goHub}>
              ← All methods
            </Button>
            <Badge variant="neutral">
              {method === "ai" ? "AI Invoice" : method === "csv" ? "CSV Upload" : "Manual Entry"}
            </Badge>
          </div>
        )}

        {error && <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

        {method === "hub" && (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-semibold">Receive Shipment</h2>
              <p className="mt-1 text-sm text-muted-foreground">Choose how you want to bring stock into the pharmacy.</p>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <MethodCard
                icon={Sparkles}
                title="AI Invoice"
                description="Upload or scan a supplier invoice. Lines are extracted and matched to the catalog when an AI key is available."
                onClick={() => startExtract("ai")}
              />
              <MethodCard
                icon={FileSpreadsheet}
                title="CSV Upload"
                description="Import a supplier invoice CSV: Quantity, Description, Rate, Discount, Amount/Extended, optional Expiry. Set your markup, review, then receive. Works offline."
                onClick={() => startExtract("csv")}
              />
              <MethodCard
                icon={Hand}
                title="Manual Entry"
                description="No document needed. Receive against an approved purchase order, or type in an ad-hoc delivery line by line."
                onClick={() => {
                  setMethod("manual")
                  setManualMode("choose")
                  setManualResult(null)
                  setError(null)
                }}
              />
            </div>
            {can("purchases.receive") && (
              <p className="text-sm text-muted-foreground">
                Approved POs can also be received from{" "}
                <Link href="/suppliers" className="text-primary underline">
                  Suppliers
                </Link>
                .
              </p>
            )}
          </div>
        )}

        {(method === "ai" || method === "csv") && (
          <ExtractFlow
            method={method}
            accept={accept}
            stage={stage}
            stageIndex={stageIndex}
            fileName={fileName}
            extracted={extracted}
            imported={imported}
            canCreate={can("inventory.create")}
            canUpdatePrices={can("inventory.update")}
            canSaveDefault={can("settings.manage")}
            onExtract={extract}
            onImported={(res) => {
              setImported(res)
              setStage("done")
              setError(null)
            }}
            onReset={() => {
              resetExtract()
              setMethod(method)
            }}
          />
        )}

        {method === "manual" && !manualResult && (
          <ManualReceiving
            mode={manualMode}
            setMode={setManualMode}
            canCreate={can("inventory.create")}
            onError={setError}
            onDone={(result) => {
              setManualResult(result)
              setError(null)
            }}
          />
        )}

        {manualResult && method === "manual" && (
          <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-border bg-card p-12 text-center animate-fade-up">
            <span className="flex size-16 items-center justify-center rounded-full bg-primary/10 text-primary">
              <CircleCheck className="size-8" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">Shipment received</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {manualResult.reference} · {manualResult.units} units across {manualResult.lines} line
                {manualResult.lines === 1 ? "" : "s"} added to inventory.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Supplier: {manualResult.supplier ?? "Not recorded"} · Purchase order: {manualResult.poNumber ?? "Not recorded"}
              </p>
            </div>
            <div className="flex gap-2">
              <ButtonLink href="/inventory" variant="outline" className="gap-1.5">
                View inventory <ArrowRight className="size-4" />
              </ButtonLink>
              <Button
                onClick={() => {
                  setManualResult(null)
                  setManualMode("choose")
                  setMethod("hub")
                }}
                className="gap-1.5"
              >
                <UploadCloud className="size-4" /> Receive another
              </Button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function MethodCard({
  icon: Icon,
  title,
  description,
  onClick,
}: {
  icon: ComponentType<{ className?: string }>
  title: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col rounded-2xl border border-border bg-card p-5 text-left transition hover:border-primary/40 hover:bg-primary/5"
    >
      <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon className="size-5" />
      </span>
      <p className="mt-4 text-base font-semibold">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </button>
  )
}

function ExtractFlow({
  method,
  accept,
  stage,
  stageIndex,
  fileName,
  extracted,
  imported,
  canCreate,
  canUpdatePrices,
  canSaveDefault,
  onExtract,
  onImported,
  onReset,
}: {
  method: "ai" | "csv"
  accept: string
  stage: Stage
  stageIndex: number
  fileName: string
  extracted: ExtractResult | null
  imported: InvoiceImportResult | null
  canCreate: boolean
  canUpdatePrices: boolean
  canSaveDefault: boolean
  onExtract: (file: File) => void
  onImported: (res: InvoiceImportResult) => void
  onReset: () => void
}) {
  return (
    <>
      <div className="flex items-center gap-2 overflow-x-auto scrollbar-thin rounded-2xl border border-border bg-card p-3">
        {extractSteps.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={cn(
                "flex size-7 items-center justify-center rounded-full text-xs font-semibold",
                i < stageIndex ? "bg-primary text-primary-foreground" : i === stageIndex ? "bg-primary/15 text-primary ring-2 ring-primary/30" : "bg-muted text-muted-foreground",
              )}
            >
              {i < stageIndex ? <Check className="size-3.5" /> : i + 1}
            </div>
            <span className={cn("whitespace-nowrap text-sm font-medium", i <= stageIndex ? "text-foreground" : "text-muted-foreground")}>{s}</span>
            {i < extractSteps.length - 1 && <span className="mx-1 h-px w-6 bg-border md:w-10" />}
          </div>
        ))}
      </div>

      {stage === "done" && imported ? (
        <ImportDone result={imported} onReset={onReset} />
      ) : stage === "review" && extracted ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles className="size-4" />
            </span>
            <div>
              <p className="text-sm font-semibold">
                Review {extracted.items.length} line{extracted.items.length === 1 ? "" : "s"} from {fileName}
              </p>
              <p className="text-xs text-muted-foreground">
                {extracted.items.filter((i) => i.matched).length} matched to inventory ·{" "}
                {extracted.items.filter((i) => !i.matched).length} not in inventory yet. Nothing is saved until you confirm.
              </p>
            </div>
          </div>
          <InvoiceReview
            result={extracted}
            canCreate={canCreate}
            canUpdatePrices={canUpdatePrices}
            canSaveDefault={canSaveDefault}
            onDone={onImported}
            onCancel={onReset}
          />
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,340px)_1fr]">
          <div className="space-y-4">
            <div className={cn("rounded-2xl border-2 border-dashed p-6 text-center", stage === "upload" ? "border-primary/40 bg-primary/5" : "border-border bg-card")}>
              <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <UploadCloud className="size-7" />
              </div>
              <p className="mt-3 text-sm font-semibold">{method === "csv" ? "Drop CSV here" : "Drop invoice here"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {method === "csv"
                  ? "Columns: Quantity, Description, Rate. Optional: Discount, Amount/Extended, Expiry, Batch. Works offline."
                  : "CSV works offline. Free-form invoice reading needs an AI key and internet."}
              </p>
              <div className="mt-4 flex flex-col gap-2">
                <label className="inline-flex">
                  <input type="file" className="hidden" accept={accept} onChange={(e) => e.target.files?.[0] && onExtract(e.target.files[0])} />
                  <span className="flex h-9 w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-primary text-sm text-primary-foreground">
                    <FileText className="size-4" /> Browse files
                  </span>
                </label>
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-card p-4">
              <p className="text-sm font-medium">Uploaded document</p>
              <div className="mt-3 flex items-center gap-3 rounded-xl border border-border bg-background p-3">
                <span className="flex size-10 items-center justify-center rounded-lg bg-secondary/10 text-secondary">
                  <FileText className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{fileName}</p>
                  <p className="text-xs text-muted-foreground">Nothing is saved until you review and confirm</p>
                </div>
                {stage !== "upload" && <CircleCheck className="size-5 text-primary" />}
              </div>
            </div>
          </div>
          <div className="rounded-2xl border border-border bg-card">
            {stage === "processing" ? (
              <div className="flex h-full min-h-80 flex-col items-center justify-center gap-4 p-10">
                <Loader2 className="size-8 animate-spin text-primary" />
                <p className="text-sm font-medium">Reading invoice…</p>
              </div>
            ) : (
              <div className="flex h-full min-h-80 flex-col items-center justify-center gap-3 p-10 text-center">
                <span className="flex size-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                  <ScanLine className="size-7" />
                </span>
                <p className="text-base font-semibold">{method === "csv" ? "Upload a CSV to begin" : "Upload an invoice to begin"}</p>
                <p className="max-w-md text-sm text-muted-foreground">
                  Rate is read as the unit cost. You choose the selling-price markup on the next screen, and medicines not yet in inventory can be
                  created there. Sample: backend/fixtures/pharmacy-invoice.csv.
                </p>
                {method === "csv" && (
                  <pre className="mt-2 rounded-lg bg-muted px-3 py-2 text-left text-xs text-muted-foreground">
                    Quantity,Description,Rate,Discount,Amount,Expiry{"\n"}10,Medicine A,5.00,,50.00,2027-04{"\n"}20,Medicine B,8.00,,160.00,
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}

function ImportDone({ result, onReset }: { result: InvoiceImportResult; onReset: () => void }) {
  const { receipt } = result
  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-8 animate-fade-up">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="flex size-16 items-center justify-center rounded-full bg-primary/10 text-primary">
          <CircleCheck className="size-8" />
        </span>
        <div>
          <h2 className="text-xl font-semibold">Invoice received</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {receipt.reference} · {receipt.units_received} units across {receipt.lines.length} line{receipt.lines.length === 1 ? "" : "s"} · invoice total{" "}
            {currency(Number(result.invoice_total))}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Supplier: {receipt.supplier_name ?? "Not recorded"} · Purchase order: {receipt.po_number ?? "Not recorded"} · Markup used:{" "}
            {result.markup_percent == null ? "none" : `${Number(result.markup_percent)}%`}
          </p>
        </div>
      </div>
      {(result.created_products.length > 0 || result.price_updates.length > 0) && (
        <div className="mx-auto grid max-w-3xl gap-3 md:grid-cols-2">
          {result.created_products.length > 0 && (
            <div className="rounded-xl border border-border p-3 text-sm">
              <p className="font-medium">New medicines created ({result.created_products.length})</p>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {result.created_products.map((p) => (
                  <li key={p.product_id}>
                    {p.product_name}: cost {currency(Number(p.cost_price))} → selling {currency(Number(p.new_selling_price))}
                    {p.price_source === "explicit" ? " (typed)" : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {result.price_updates.length > 0 && (
            <div className="rounded-xl border border-border p-3 text-sm">
              <p className="font-medium">Selling prices updated ({result.price_updates.length})</p>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {result.price_updates.map((p) => (
                  <li key={p.product_id}>
                    {p.product_name}: {currency(Number(p.old_selling_price ?? 0))} → {currency(Number(p.new_selling_price))}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <div className="flex justify-center gap-2">
        <ButtonLink href="/inventory" variant="outline" className="gap-1.5">
          View inventory <ArrowRight className="size-4" />
        </ButtonLink>
        <Button onClick={onReset} className="gap-1.5">
          <UploadCloud className="size-4" /> Receive another
        </Button>
      </div>
    </div>
  )
}

function ManualReceiving({
  mode,
  setMode,
  canCreate,
  onError,
  onDone,
}: {
  mode: ManualMode
  setMode: (m: ManualMode) => void
  canCreate: boolean
  onError: (msg: string | null) => void
  onDone: (result: ManualResult) => void
}) {
  if (mode === "choose") {
    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold">Manual Entry</h2>
          <p className="mt-1 text-sm text-muted-foreground">Receive against an approved PO, or enter an ad-hoc delivery without any document.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <MethodCard
            icon={ClipboardList}
            title="Receive from Purchase Order"
            description="Select an approved or partially received PO and record quantities, batches, and expiry."
            onClick={() => setMode("po")}
          />
          <MethodCard
            icon={Hand}
            title="Ad-hoc delivery (no PO)"
            description="Search or create medicines, then enter quantity, batch, expiry, and cost per line. Supplier is optional; if left blank it is recorded as “Not recorded”."
            onClick={() => setMode("adhoc")}
          />
        </div>
      </div>
    )
  }

  if (mode === "po") {
    return <ManualFromPO onBack={() => setMode("choose")} onError={onError} onDone={onDone} />
  }

  return <ManualAdhoc canCreate={canCreate} onBack={() => setMode("choose")} onError={onError} onDone={onDone} />
}

function ManualFromPO({
  onBack,
  onError,
  onDone,
}: {
  onBack: () => void
  onError: (msg: string | null) => void
  onDone: (result: ManualResult) => void
}) {
  const [pos, setPos] = useState<PurchaseOrder[]>([])
  const [selected, setSelected] = useState<PurchaseOrder | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api<PurchaseOrder[]>("/purchase-orders?status=APPROVED"),
      api<PurchaseOrder[]>("/purchase-orders?status=PARTIALLY_RECEIVED"),
    ])
      .then(([a, b]) => setPos([...a, ...b]))
      .catch((err) => onError(err instanceof ApiError ? err.message : "Could not load purchase orders"))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          ← Manual options
        </Button>
        <h2 className="text-lg font-semibold">Receive from Purchase Order</h2>
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading approved orders…</p>
      ) : !pos.length ? (
        <div className="rounded-2xl border border-border bg-card p-8 text-center">
          <p className="font-medium">No approved orders ready to receive</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create and approve a PO from{" "}
            <Link href="/suppliers" className="text-primary underline">
              Suppliers
            </Link>
            , then return here.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">PO</th>
                <th className="px-4 py-3 font-medium">Supplier</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Lines</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {pos.map((po) => (
                <tr key={po.id}>
                  <td className="px-4 py-3 font-mono text-xs">{po.po_number}</td>
                  <td className="px-4 py-3">{po.supplier_name ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant={po.status === "APPROVED" ? "success" : "warning"}>{po.status.replace("_", " ")}</Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{po.items.length}</td>
                  <td className="px-4 py-3 text-right">
                    <Button type="button" size="sm" onClick={() => setSelected(po)}>
                      Receive
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <ReceivePOForm
          po={selected}
          onClose={() => setSelected(null)}
          onSaved={(po, units, lines) => {
            setSelected(null)
            onDone({ reference: po.po_number, poNumber: po.po_number, supplier: po.supplier_name ?? null, units, lines })
          }}
          onError={onError}
        />
      )}
    </div>
  )
}

function ReceivePOForm({
  po,
  onClose,
  onSaved,
  onError,
}: {
  po: PurchaseOrder
  onClose: () => void
  onSaved: (po: PurchaseOrder, units: number, lines: number) => void
  onError: (msg: string | null) => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [detail, setDetail] = useState(po)

  useEffect(() => {
    api<PurchaseOrder>(`/purchase-orders/${po.id}`)
      .then(setDetail)
      .catch(() => setDetail(po))
  }, [po])

  return (
    <Overlay onClose={onClose}>
      <form
        className="max-h-[90vh] w-full max-w-2xl space-y-3 overflow-y-auto rounded-2xl border border-border bg-card p-6"
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault()
          const fd = new FormData(e.currentTarget)
          const lines = detail.items
            .map((item) => ({
              item_id: item.id,
              quantity: Number(fd.get(`qty-${item.id}`) || 0),
              batch_number: String(fd.get(`batch-${item.id}`) || item.batch_number || ""),
              expiry_date: normalizeExpiryInput(String(fd.get(`expiry-${item.id}`) || item.expiry_date || "")) || null,
              unit_cost: fd.get(`cost-${item.id}`) ? String(fd.get(`cost-${item.id}`)) : undefined,
              notes: String(fd.get(`notes-${item.id}`) || "").trim(),
            }))
            .filter((line) => line.quantity > 0)
          if (!lines.length) {
            setError("Enter a quantity to receive")
            return
          }
          const missing = lines.find((line) => !line.batch_number.trim() || !line.expiry_date)
          if (missing) {
            const name = detail.items.find((i) => i.id === missing.item_id)?.product_name ?? "a line"
            setError(`Batch number and expiry are required for ${name}`)
            return
          }
          setSaving(true)
          setError(null)
          onError(null)
          try {
            const updated = await api<PurchaseOrder>(`/purchase-orders/${detail.id}/receive`, {
              method: "POST",
              body: JSON.stringify({ lines }),
            })
            onSaved(updated, lines.reduce((sum, line) => sum + line.quantity, 0), lines.length)
          } catch (err) {
            const msg = err instanceof ApiError ? err.message : "Receive failed"
            setError(msg)
            onError(msg)
          } finally {
            setSaving(false)
          }
        }}
      >
        <div>
          <h2 className="text-lg font-semibold">Receive {detail.po_number}</h2>
          <p className="text-sm text-muted-foreground">{detail.supplier_name ?? "Supplier"}</p>
        </div>
        {detail.items.map((item) => {
          const remaining = item.quantity_ordered - item.quantity_received
          return (
            <div key={item.id} className="space-y-2 rounded-xl border border-border p-3">
              <p className="text-sm font-medium">{item.product_name}</p>
              <p className="text-xs text-muted-foreground">
                Ordered {item.quantity_ordered} · Received {item.quantity_received} · Remaining {remaining}
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <input name={`qty-${item.id}`} type="number" min={0} max={remaining} defaultValue={remaining} placeholder="Qty" className="h-9 rounded-lg border border-border px-3 text-sm" />
                <input name={`batch-${item.id}`} defaultValue={item.batch_number} placeholder="Batch" className="h-9 rounded-lg border border-border px-3 text-sm" />
                <input name={`expiry-${item.id}`} type="date" min="2000-01-01" max="2099-12-31" defaultValue={item.expiry_date ?? ""} className="h-9 rounded-lg border border-border px-3 text-sm" />
                <input name={`cost-${item.id}`} defaultValue={String(item.unit_cost)} placeholder="Unit cost" className="h-9 rounded-lg border border-border px-3 text-sm" />
              </div>
              <input name={`notes-${item.id}`} maxLength={200} placeholder="Line notes (optional, e.g. 2 boxes damaged)" className="h-9 w-full rounded-lg border border-border px-3 text-sm" />
            </div>
          )
        })}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Receiving…" : "Receive shipment"}
          </Button>
        </div>
      </form>
    </Overlay>
  )
}

function ManualAdhoc({
  canCreate,
  onBack,
  onError,
  onDone,
}: {
  canCreate: boolean
  onBack: () => void
  onError: (msg: string | null) => void
  onDone: (result: ManualResult) => void
}) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [supplierId, setSupplierId] = useState("")
  const [notes, setNotes] = useState("")
  const [lines, setLines] = useState<AdhocLine[]>([emptyAdhoc()])
  const [creating, setCreating] = useState<{ key: string | null; name: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [lineErrors, setLineErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    api<Supplier[]>("/suppliers").then(setSuppliers).catch(() => setSuppliers([]))
  }, [])

  const updateLine = (key: string, patch: Partial<AdhocLine>) => {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)))
    setLineErrors((current) => {
      if (!current[key]) return current
      const next = { ...current }
      delete next[key]
      return next
    })
  }

  const pickProduct = (key: string, product: Product) => {
    updateLine(key, {
      product: { id: product.id, name: product.name, sku: product.sku },
      unit_cost: String(product.cost_price ?? "0"),
    })
  }

  const applyCreated = (product: Product) => {
    const key = creating?.key
    setLines((current) => {
      const target = key ?? current.find((l) => !l.product)?.key
      if (!target) return [...current, { ...emptyAdhoc(), product: { id: product.id, name: product.name, sku: product.sku }, unit_cost: String(product.cost_price ?? "0") }]
      return current.map((line) =>
        line.key === target
          ? { ...line, product: { id: product.id, name: product.name, sku: product.sku }, unit_cost: String(product.cost_price ?? "0") }
          : line,
      )
    })
    setCreating(null)
  }

  const validate = () => {
    const errors: Record<string, string> = {}
    const filled = lines.filter((l) => l.product || l.batch_number || l.expiry_date)
    for (const line of filled) {
      const qty = Number(line.quantity)
      const cost = Number(line.unit_cost)
      if (!line.product) errors[line.key] = "Choose a medicine"
      else if (!Number.isInteger(qty) || qty <= 0) errors[line.key] = "Quantity must be a whole number above 0"
      else if (!line.batch_number.trim()) errors[line.key] = "Batch number is required"
      else if (!line.expiry_date) errors[line.key] = "Expiry date is required"
      else if (line.unit_cost === "" || Number.isNaN(cost) || cost < 0) errors[line.key] = "Enter a unit cost (0 or more)"
    }
    setLineErrors(errors)
    return { errors, filled }
  }

  const submit = async () => {
    const { errors, filled } = validate()
    if (!filled.length) {
      setLocalError("Add at least one line")
      return
    }
    if (Object.keys(errors).length) {
      setLocalError("Fix the highlighted lines. Nothing has been received yet.")
      return
    }
    setSaving(true)
    setLocalError(null)
    onError(null)
    try {
      const receipt = await api<ReceiptResult>("/receiving/adhoc", {
        method: "POST",
        body: JSON.stringify({
          supplier_id: supplierId || null,
          notes: notes.trim(),
          items: filled.map((line) => ({
            product_id: line.product!.id,
            quantity: Number(line.quantity),
            unit_cost: line.unit_cost,
            batch_number: line.batch_number.trim(),
            expiry_date: normalizeExpiryInput(line.expiry_date),
            notes: line.notes.trim(),
          })),
        }),
      })
      onDone({
        reference: receipt.reference,
        supplier: receipt.supplier_name,
        poNumber: receipt.po_number,
        units: receipt.units_received,
        lines: receipt.lines.length,
      })
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Receive failed"
      setLocalError(`${msg}. Nothing was received.`)
      onError(null)
    } finally {
      setSaving(false)
    }
  }

  const totalUnits = lines.reduce((sum, l) => sum + (l.product ? Number(l.quantity) || 0 : 0), 0)
  const totalCost = lines.reduce((sum, l) => sum + (l.product ? (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0) : 0), 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          ← Manual options
        </Button>
        <h2 className="text-lg font-semibold">Ad-hoc delivery (no PO)</h2>
      </div>
      <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            Supplier (optional)
            <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className="h-10 rounded-lg border border-border px-3 text-sm">
              <option value="">Not recorded (unknown supplier)</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground">
              {supplierId
                ? "An approved purchase order is created for this delivery so the supplier is traceable."
                : "No purchase order is created. Batch supplier will show as “Not recorded”."}
            </span>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Delivery notes (optional)
            <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} placeholder="e.g. Walk-in delivery, invoice to follow" className="h-10 rounded-lg border border-border px-3 text-sm" />
          </label>
        </div>
        <div className="rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Medicine</th>
                <th className="px-3 py-2 font-medium">Qty</th>
                <th className="px-3 py-2 font-medium">Batch</th>
                <th className="px-3 py-2 font-medium">Expiry</th>
                <th className="px-3 py-2 font-medium">Unit cost</th>
                <th className="px-3 py-2 font-medium">Notes</th>
                <th className="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {lines.map((line, index) => (
                <tr key={line.key} className={lineErrors[line.key] ? "bg-destructive/5" : ""}>
                  <td className="px-2 py-2 align-top">
                    <div className="min-w-56">
                      <ProductPicker
                        value={line.product}
                        onSelect={(p) => pickProduct(line.key, p)}
                        onClear={() => updateLine(line.key, { product: null })}
                        onCreateNew={canCreate ? (name) => setCreating({ key: line.key, name }) : undefined}
                        placeholder={`Line ${index + 1}: search medicine…`}
                      />
                      {line.product && <p className="mt-1 text-xs text-muted-foreground">{line.product.sku}</p>}
                      {lineErrors[line.key] && <p className="mt-1 text-xs text-destructive">{lineErrors[line.key]}</p>}
                    </div>
                  </td>
                  <td className="px-2 py-2 align-top">
                    <input value={line.quantity} onChange={(e) => updateLine(line.key, { quantity: e.target.value })} type="number" min={1} step={1} className="h-9 w-20 rounded-lg border border-border px-2 text-sm" aria-label="Quantity" />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <input value={line.batch_number} onChange={(e) => updateLine(line.key, { batch_number: e.target.value })} placeholder="LOT-001" className="h-9 w-28 rounded-lg border border-border px-2 text-sm" aria-label="Batch number" />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <input value={line.expiry_date} onChange={(e) => updateLine(line.key, { expiry_date: e.target.value })} type="date" min="2000-01-01" max="2099-12-31" className="h-9 rounded-lg border border-border px-2 text-sm" aria-label="Expiry date" />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <input value={line.unit_cost} onChange={(e) => updateLine(line.key, { unit_cost: e.target.value })} inputMode="decimal" placeholder="0.00" className="h-9 w-24 rounded-lg border border-border px-2 text-sm" aria-label="Unit cost" />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <input value={line.notes} onChange={(e) => updateLine(line.key, { notes: e.target.value })} maxLength={200} placeholder="Optional" className="h-9 w-36 rounded-lg border border-border px-2 text-sm" aria-label="Line notes" />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <button
                      type="button"
                      className="h-9 text-muted-foreground hover:text-destructive"
                      onClick={() => setLines((c) => (c.length === 1 ? [emptyAdhoc()] : c.filter((l) => l.key !== line.key)))}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setLines((c) => [...c, emptyAdhoc()])}>
            Add line
          </Button>
          {canCreate && (
            <Button type="button" variant="outline" size="sm" onClick={() => setCreating({ key: null, name: "" })}>
              Create new medicine
            </Button>
          )}
          <span className="ml-auto text-sm text-muted-foreground">
            {totalUnits} units · {currency(totalCost)}
          </span>
          <Button type="button" disabled={saving} onClick={submit}>
            {saving ? "Receiving…" : "Receive delivery"}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          All lines are validated together. If any line is invalid, nothing is received.
        </p>
        {localError && <p className="text-sm text-destructive">{localError}</p>}
      </div>
      {creating && (
        <QuickAddProduct
          catalogOnly
          title="Create new medicine"
          initialName={creating.name}
          defaultSupplierId={supplierId || null}
          onClose={() => setCreating(null)}
          onSaved={applyCreated}
        />
      )}
    </div>
  )
}
