import type { Product } from "./types"

export type Medicine = {
  id: string
  name: string
  brand: string
  barcode: string
  category: string
  supplier: string
  batch: string
  expiry: string
  quantity: number
  reorderPoint: number
  price: number
  cost: number
  status: "healthy" | "low" | "critical"
  raw: Product
}

export function asMedicine(p: Product): Medicine {
  return {
    id: p.id,
    name: p.name,
    brand: p.brand,
    barcode: p.barcode,
    category: p.category,
    supplier: p.supplier_name ?? "",
    batch: p.nearest_batch ?? "",
    expiry: p.nearest_expiry ?? "",
    quantity: Number(p.quantity_on_hand),
    reorderPoint: Number(p.reorder_threshold),
    price: Number(p.selling_price),
    cost: Number(p.cost_price),
    status: p.status,
    raw: p,
  }
}
