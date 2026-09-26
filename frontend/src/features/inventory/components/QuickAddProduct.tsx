"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { api, ApiError } from "@/lib/api/client"
import type { Product } from "@/lib/api/types"
import { normalizeExpiryInput } from "@/lib/format"

type Props = {
  onClose: () => void
  onSaved: (product: Product) => void
  /** When true, opening stock fields are hidden (catalog-only create for PO/receiving). */
  catalogOnly?: boolean
  title?: string
  defaultSupplierId?: string | null
  /** Prefills the name field, e.g. with what the user typed into a product search. */
  initialName?: string
}

const inputCls = "h-9 rounded-lg border border-border px-3 text-sm outline-none"

/** Shared medicine create form. Always starts at quantity 0 unless opening qty is provided. */
export function QuickAddProduct({
  onClose,
  onSaved,
  catalogOnly = false,
  title = "Add medicine",
  defaultSupplierId = null,
  initialName = "",
}: Props) {
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [showMore, setShowMore] = useState(false)

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const openingQty = catalogOnly ? 0 : Number(fd.get("qty") || 0)
    setSaving(true)
    setError(null)
    try {
      const product = await api<Product>("/products", {
        method: "POST",
        body: JSON.stringify({
          sku: String(fd.get("sku") || "").trim() || null,
          barcode: String(fd.get("barcode") || "").trim() || null,
          name: String(fd.get("name") || "").trim(),
          brand: String(fd.get("brand") || "").trim(),
          category: String(fd.get("category") || "").trim() || "General",
          generic_name: String(fd.get("generic_name") || "").trim(),
          dosage_form: String(fd.get("dosage_form") || "").trim(),
          strength: String(fd.get("strength") || "").trim(),
          unit: String(fd.get("unit") || "").trim() || "tablet",
          description: String(fd.get("description") || "").trim(),
          selling_price: String(fd.get("price") || "").trim(),
          cost_price: String(fd.get("cost") || "").trim(),
          reorder_threshold: Number(fd.get("reorder")),
          supplier_id: defaultSupplierId || undefined,
          initial_quantity: openingQty,
          batch_number: catalogOnly ? "" : fd.get("batch") || "",
          expiry_date: !catalogOnly && fd.get("expiry") ? normalizeExpiryInput(String(fd.get("expiry"))) : null,
        }),
      })
      onSaved(product)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Overlay onClose={onClose}>
      <form onSubmit={submit} onClick={(e) => e.stopPropagation()} className="w-full max-w-lg space-y-3 rounded-2xl border border-border bg-card p-6">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Fields marked * are required. SKU, barcode, brand, and category can be added later.
            {catalogOnly ? " Stock stays at zero until you receive a shipment." : ""}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="col-span-2 flex flex-col gap-1 text-sm">
            Medicine name *
            <input name="name" placeholder="Amoxicillin 500mg" defaultValue={initialName} maxLength={200} className={inputCls} required autoFocus />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Cost price *
            <input name="cost" type="number" min={0} step="any" inputMode="decimal" placeholder="0.18" className={inputCls} required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Selling price *
            <input name="price" type="number" min={0} step="any" inputMode="decimal" placeholder="0.35" className={inputCls} required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Reorder point *
            <input name="reorder" type="number" min={0} step={1} placeholder="100" className={inputCls} required />
          </label>
          <span />
          {[
            ["brand", "Brand / manufacturer (optional)", "Amoxil"],
            ["sku", "SKU (optional)", "MD-2001"],
            ["barcode", "Barcode (optional)", "8901234500999"],
            ["category", "Category (optional)", "General"],
          ].map(([name, label, ph]) => (
            <label key={name} className="flex flex-col gap-1 text-sm">
              {label}
              <input name={name} placeholder={ph} className={inputCls} />
            </label>
          ))}
          <button
            type="button"
            onClick={() => setShowMore((v) => !v)}
            className="col-span-2 text-left text-xs font-medium text-primary hover:underline"
          >
            {showMore ? "Hide optional details" : "More details (optional): generic name, dosage form, strength, unit, description"}
          </button>
          <div className={showMore ? "col-span-2 grid grid-cols-2 gap-3" : "hidden"}>
            {[
              ["generic_name", "Generic name", "Amoxicillin"],
              ["dosage_form", "Dosage form", "Capsule"],
              ["strength", "Strength", "500mg"],
              ["unit", "Unit", "tablet"],
            ].map(([name, label, ph]) => (
              <label key={name} className="flex flex-col gap-1 text-sm">
                {label}
                <input name={name} placeholder={ph} className={inputCls} />
              </label>
            ))}
            <label className="col-span-2 flex flex-col gap-1 text-sm">
              Description
              <textarea name="description" rows={2} className="rounded-lg border border-border px-3 py-2 text-sm outline-none" />
            </label>
          </div>
          {!catalogOnly && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                Opening qty
                <input name="qty" type="number" min={0} defaultValue={0} placeholder="0" className="h-9 rounded-lg border border-border px-3 text-sm outline-none" />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Batch
                <input name="batch" placeholder="Only if opening qty &gt; 0" className="h-9 rounded-lg border border-border px-3 text-sm outline-none" />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Expiry
                <input name="expiry" type="date" min="2000-01-01" max="2099-12-31" className="h-9 rounded-lg border border-border px-3 text-sm outline-none" />
              </label>
            </>
          )}
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
