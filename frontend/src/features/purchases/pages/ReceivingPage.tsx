"use client"

import { useState } from "react"
import Link from "next/link"
import { UploadCloud, Camera, FileText, Sparkles, Check, X, ScanLine, Loader2, CircleCheck, PackageCheck, ArrowRight } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button, ButtonLink } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api/client"
import type { ExtractedItem, PurchaseOrder } from "@/lib/api/types"
import { currency, normalizeExpiryInput } from "@/lib/format"
import { cn } from "@/lib/utils"

type Stage = "upload" | "processing" | "review" | "done"
const steps = ["Upload invoice", "AI extraction", "Review & approve", "Imported"]

export default function ReceivingPage() {
  const [stage, setStage] = useState<Stage>("upload")
  const [items, setItems] = useState<ExtractedItem[]>([])
  const [supplierId, setSupplierId] = useState<string | null>(null)
  const [supplierName, setSupplierName] = useState<string | null>(null)
  const [fileName, setFileName] = useState("No file selected")
  const [error, setError] = useState<string | null>(null)
  const [imported, setImported] = useState<PurchaseOrder | null>(null)

  const extract = async (file: File) => {
    setFileName(file.name)
    setStage("processing")
    setError(null)
    const fd = new FormData()
    fd.append("file", file)
    try {
      const res = await api<{ supplier_id: string | null; supplier_name: string | null; items: ExtractedItem[] }>("/receiving/extract", { method: "POST", body: fd })
      setItems(res.items)
      setSupplierId(res.supplier_id)
      setSupplierName(res.supplier_name)
      setStage("review")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not read invoice")
      setStage("upload")
    }
  }

  const approved = items.filter((i) => i.matched)
  const total = approved.reduce((a, b) => a + b.quantity * Number(b.unit_cost), 0)
  const stageIndex = stage === "upload" ? 0 : stage === "processing" ? 1 : stage === "review" ? 2 : 3

  const importNow = async () => {
    if (!supplierId) {
      setError("No supplier matched. Assign products to catalog items first.")
      return
    }
    try {
      const po = await api<PurchaseOrder>("/receiving/import", {
        method: "POST",
        body: JSON.stringify({
          supplier_id: supplierId,
          items: approved.map((i) => ({
            product_id: i.product_id,
            product_name: i.name,
            quantity_ordered: i.quantity,
            unit_cost: i.unit_cost,
            batch_number: i.batch,
            expiry_date: i.expiry ? normalizeExpiryInput(i.expiry) : null,
          })),
        }),
      })
      setImported(po)
      setStage("done")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed")
    }
  }

  return (
    <>
      <AppTopbar title="Receive Shipment" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        <div className="flex items-center gap-2 overflow-x-auto scrollbar-thin rounded-2xl border border-border bg-card p-3">
          {steps.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={cn("flex size-7 items-center justify-center rounded-full text-xs font-semibold", i < stageIndex ? "bg-primary text-primary-foreground" : i === stageIndex ? "bg-primary/15 text-primary ring-2 ring-primary/30" : "bg-muted text-muted-foreground")}>
                {i < stageIndex ? <Check className="size-3.5" /> : i + 1}
              </div>
              <span className={cn("whitespace-nowrap text-sm font-medium", i <= stageIndex ? "text-foreground" : "text-muted-foreground")}>{s}</span>
              {i < steps.length - 1 && <span className="mx-1 h-px w-6 bg-border md:w-10" />}
            </div>
          ))}
        </div>
        {error && <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

        {stage === "done" && imported ? (
          <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-border bg-card p-12 text-center animate-fade-up">
            <span className="flex size-16 items-center justify-center rounded-full bg-primary/10 text-primary"><CircleCheck className="size-8" /></span>
            <div>
              <h2 className="text-xl font-semibold">Shipment imported</h2>
              <p className="mt-1 text-sm text-muted-foreground">{imported.po_number} · {approved.length} medicines worth {currency(total)} were added to inventory.</p>
            </div>
            <div className="flex gap-2">
              <ButtonLink href="/inventory" variant="outline" className="gap-1.5">View inventory <ArrowRight className="size-4" /></ButtonLink>
              <Button onClick={() => { setStage("upload"); setItems([]); setImported(null) }} className="gap-1.5"><UploadCloud className="size-4" /> Receive another</Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,340px)_1fr]">
            <div className="space-y-4">
              <div className={cn("rounded-2xl border-2 border-dashed p-6 text-center", stage === "upload" ? "border-primary/40 bg-primary/5" : "border-border bg-card")}>
                <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary"><UploadCloud className="size-7" /></div>
                <p className="mt-3 text-sm font-semibold">Drop invoice here</p>
                <p className="mt-1 text-xs text-muted-foreground">Use a CSV with columns name, quantity, unit_cost, batch, expiry. That works offline. Free-form invoice reading needs an AI key and internet.</p>
                <div className="mt-4 flex flex-col gap-2">
                  <label className="inline-flex">
                    <input type="file" className="hidden" accept=".csv,text/csv,.txt" onChange={(e) => e.target.files?.[0] && extract(e.target.files[0])} />
                    <span className="flex h-9 w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-primary text-sm text-primary-foreground">
                      <FileText className="size-4" /> Browse files
                    </span>
                  </label>
                </div>
              </div>
              <div className="rounded-2xl border border-border bg-card p-4">
                <p className="text-sm font-medium">Uploaded document</p>
                <div className="mt-3 flex items-center gap-3 rounded-xl border border-border bg-background p-3">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-secondary/10 text-secondary"><FileText className="size-5" /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{fileName}</p>
                    <p className="text-xs text-muted-foreground">{supplierName ?? "Supplier unmatched until extract"}</p>
                  </div>
                  {stage !== "upload" && <CircleCheck className="size-5 text-primary" />}
                </div>
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-card">
              {stage === "upload" && (
                <div className="flex h-full min-h-80 flex-col items-center justify-center gap-3 p-10 text-center">
                  <span className="flex size-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground"><ScanLine className="size-7" /></span>
                  <p className="text-base font-semibold">Upload an invoice to begin</p>
                  <p className="max-w-sm text-sm text-muted-foreground">AetherQore matches CSV line items to inventory and prepares a one-click import. A sample file lives in backend/fixtures/sample-invoice.csv. Cloud invoice reading is optional and will not run without internet.</p>
                </div>
              )}
              {stage === "processing" && (
                <div className="flex h-full min-h-80 flex-col items-center justify-center gap-4 p-10">
                  <Loader2 className="size-8 animate-spin text-primary" />
                  <p className="text-sm font-medium">Reading invoice…</p>
                </div>
              )}
              {stage === "review" && (
                <div className="flex h-full flex-col">
                  <div className="flex items-center gap-3 border-b border-border p-4">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sparkles className="size-4" /></span>
                    <div>
                      <p className="text-sm font-semibold">Extracted {items.length} line items</p>
                      <p className="text-xs text-muted-foreground">Unmatched rows stay amber until they exist in inventory</p>
                    </div>
                    <Badge variant="success" className="ml-auto"><Check className="size-3" /> {approved.length} matched</Badge>
                  </div>
                  <div className="flex-1 space-y-2.5 overflow-y-auto p-4">
                    {items.map((it, idx) => (
                      <div key={`${it.name}-${idx}`} className={cn("rounded-xl border p-3.5", it.matched ? "border-border bg-background" : "border-warning/40 bg-warning/5")}>
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{it.name}</p>
                          <Badge variant={it.confidence >= 0.9 ? "success" : "warning"}>{Math.round(it.confidence * 100)}%</Badge>
                          {!it.matched && <Badge variant="neutral">Needs catalog match</Badge>}
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-4 text-xs text-muted-foreground sm:grid-cols-4">
                          <span>Qty <span className="font-medium text-foreground">{it.quantity}</span></span>
                          <span>Unit <span className="font-medium text-foreground">{currency(Number(it.unit_cost))}</span></span>
                          <span>Batch <span className="font-mono text-foreground">{it.batch}</span></span>
                          <span>Exp <span className="text-foreground">{it.expiry ?? "—"}</span></span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center gap-3 border-t border-border p-4">
                    <div>
                      <p className="text-xs text-muted-foreground">Matched shipment value</p>
                      <p className="text-lg font-semibold">{currency(total)}</p>
                    </div>
                    <Button className="ml-auto gap-1.5" disabled={!approved.length} onClick={importNow}>
                      <PackageCheck className="size-4" /> Import {approved.length} to inventory
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
