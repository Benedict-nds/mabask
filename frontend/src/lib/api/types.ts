export type RoleName = "admin" | "pharmacist" | "cashier"
export type MedStatus = "healthy" | "low" | "critical"

export type User = {
  id: string
  email: string
  full_name: string
  role: RoleName
  permissions: string[]
  is_active: boolean
  last_login_at?: string | null
}

export type Role = {
  name: RoleName
  description: string
  permissions: string[]
}

export type AuditEntry = {
  id: string
  user_id: string | null
  actor: string | null
  action: string
  entity_type: string
  entity_id: string
  details: Record<string, unknown>
  created_at: string
}

export type InventoryCounts = {
  total: number
  healthy: number
  low: number
  critical: number
}

export type AuthResponse = {
  tokens: { access_token: string; refresh_token: string; token_type: string }
  user: User
}

export type Page<T> = { items: T[]; total: number; limit: number; offset: number }

export type Batch = {
  id: string
  batch_number: string
  expiry_date: string
  quantity: number
  cost_price: number
}

export type Product = {
  id: string
  sku: string
  barcode: string
  name: string
  generic_name: string
  brand: string
  category: string
  description: string
  dosage_form: string
  strength: string
  unit: string
  cost_price: number
  selling_price: number
  quantity_on_hand: number
  reorder_threshold: number
  supplier_id: string | null
  supplier_name: string | null
  is_active: boolean
  status: MedStatus
  nearest_expiry: string | null
  nearest_batch: string | null
  batches: Batch[]
}

export type Supplier = {
  id: string
  name: string
  contact_name: string
  email: string
  phone: string
  address: string
  status: "preferred" | "active" | "review" | "inactive"
  rating: number
  on_time_rate: number
  notes: string
  active_skus: number
  outstanding: number
  last_delivery: string | null
}

export type ExtractedItem = {
  name: string
  quantity: number
  unit_cost: number
  batch: string
  expiry: string | null
  confidence: number
  matched: boolean
  product_id: string | null
}

export type POItem = {
  id: string
  product_id: string | null
  product_name: string
  quantity_ordered: number
  quantity_received: number
  unit_cost: number
  batch_number: string
  expiry_date: string | null
}

export type PurchaseOrder = {
  id: string
  po_number: string
  supplier_id: string
  supplier_name: string | null
  status: string
  notes: string
  subtotal: number
  total: number
  created_at: string
  items: POItem[]
}

export type SaleItem = {
  id: string
  product_id: string
  product_name: string | null
  barcode: string | null
  quantity: number
  quantity_returned: number
  unit_price: number
  line_total: number
  returnable: number
}

export type Sale = {
  id: string
  sale_number: string
  customer_id: string | null
  customer_name: string | null
  cashier_name: string | null
  status: string
  subtotal: number
  discount_percent: number
  discount_amount: number
  tax_rate: number
  tax_amount: number
  total: number
  payment_method: string
  amount_tendered: number
  change_due: number
  created_at: string
  items: SaleItem[]
}

export type Customer = {
  id: string
  name: string
  phone: string
  email: string
  notes: string
}

export type Settings = {
  pharmacy_name: string
  license_number: string
  phone: string
  email: string
  address: string
  tax_rate: number
  currency: string
}

export type CopilotAnswer = {
  text: string
  table?: { head: string[]; rows: string[][] } | null
  actions: string[]
  followups: string[]
  source: string
  llm_used?: boolean
}

export type CopilotStatus = {
  ai_enabled: boolean
  mode: "llm" | "local-data"
  message: string
}

export type Health = {
  status: string
  service: string
  environment?: string
  database?: string
  ai?: { enabled: boolean; mode: string }
}

export type Dashboard = {
  today_revenue: number
  today_sales_count: number
  yesterday_revenue: number
  yesterday_change_pct: number
  inventory_value: number
  low_stock_count: number
  expiring_count: number
  pending_invoices: number
  weekly_revenue: number
  weekly_trend: { label: string; value: number }[]
  insights: { text: string; action: string; href: string }[]
  activity: { id: string; who: string; action: string; time: string; type: string }[]
}

export type SalesReport = {
  range: string
  revenue: number
  transactions: number
  average_ticket: number
  gross_profit: number
  units_sold: number
  payment_methods: Record<string, number>
  top_selling: { name: string; units: number; revenue: number; change: number }[]
  trend: { label: string; value: number }[]
  category_mix: { label: string; value: number; color: string }[]
}

export type Notification = {
  id: string
  title: string
  message: string
  kind: string
  is_read: boolean
}
