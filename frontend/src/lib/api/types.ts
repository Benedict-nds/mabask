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
  permission_overrides?: Record<string, "ALLOW" | "DENY">
}

export type OverrideState = "INHERIT" | "ALLOW" | "DENY"

export type PermissionInfo = {
  code: string
  description: string
  group: string
  group_label: string
  admin_only: boolean
}

export type UserPermissionEntry = PermissionInfo & {
  role_default: boolean
  override: OverrideState
  effective: boolean
  locked: boolean
  locked_reason?: string | null
}

export type UserPermissions = {
  user_id: string
  full_name: string
  role: RoleName
  editable: boolean
  not_editable_reason?: string | null
  override_count: number
  permissions: UserPermissionEntry[]
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
  entity_label?: string | null
  details: Record<string, unknown>
  created_at: string
}

export type AuditFacets = {
  actions: string[]
  entity_types: string[]
  users: { id: string; name: string }[]
}

export type ReceiptResult = {
  reference: string
  receipt_id?: string | null
  purchase_order_id: string | null
  po_number: string | null
  supplier_id: string | null
  supplier_name: string | null
  units_received: number
  lines: {
    product_id: string
    product_name: string
    batch_id: string
    batch_number: string
    expiry_date: string
    quantity: number
    unit_cost: number
  }[]
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
  supplier?: { id: string; name: string } | null
  purchase_order?: { id: string; po_number: string } | null
  received_at?: string | null
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
  deleted_at?: string | null
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
  row?: number | null
  description?: string
  discount?: number | string | null
  amount?: number | string | null
  selling_price?: number | string | null
  expiry_raw?: string
  issues?: string[]
  product_sku?: string
  current_cost_price?: number | string | null
  current_selling_price?: number | string | null
  archived_product_id?: string | null
  archived_product_name?: string | null
}

export type DiscountMode = "percent" | "amount"

export type ExtractResult = {
  supplier_id: string | null
  supplier_name: string | null
  items: ExtractedItem[]
  source: "csv" | "ai"
  columns: Record<string, string>
  ignored_columns: string[]
  discount_mode: DiscountMode
  discount_mode_source: string
  skipped_rows: { row: number; reason: string; text: string }[]
  default_markup_percent: number | string | null
}

export type InvoicePrice = {
  product_id: string
  product_name: string
  cost_price: number | string
  old_selling_price: number | string | null
  new_selling_price: number | string
  price_source: "explicit" | "markup"
}

export type InvoiceImportResult = {
  receipt: ReceiptResult
  markup_percent: number | string | null
  discount_mode: DiscountMode
  invoice_total: number | string
  created_products: InvoicePrice[]
  price_updates: InvoicePrice[]
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
  review_comment?: string
  review_requested_by?: string | null
  review_requested_by_name?: string | null
  review_requested_at?: string | null
  subtotal: number
  total: number
  created_by?: string
  created_by_name?: string | null
  created_at: string
  items: POItem[]
}

export type SaleItem = {
  id: string
  product_id: string
  product_name: string | null
  product_sku?: string | null
  barcode: string | null
  batch_id?: string | null
  batch_number?: string | null
  batch_expiry?: string | null
  batch_cost_price?: number | null
  batch_supplier_id?: string | null
  batch_supplier_name?: string | null
  batch_po_id?: string | null
  batch_po_number?: string | null
  quantity: number
  quantity_returned: number
  unit_price: number
  line_total: number
  returnable: number
}

export type SaleCorrectionLink = {
  request_id: string
  reference?: string
  status: string
  corrected_sale_id?: string | null
  corrected_sale_number?: string | null
  original_sale_id?: string | null
  original_sale_number?: string | null
  financial_difference?: number | null
  return_id?: string | null
  return_number?: string | null
  refund_amount?: number | null
  reason?: string | null
  requested_by_name?: string | null
  requested_at?: string | null
  reviewed_by_name?: string | null
  reviewed_at?: string | null
  review_note?: string | null
}

export type SaleReturnSummary = {
  id: string
  return_number: string
  reason: string
  refund_amount: number
  restock: boolean
  created_at: string
  processed_by_name?: string | null
  items?: { product_id: string; product_name: string | null; quantity: number; unit_price: number }[]
}

export type SaleMovement = {
  id: string
  product_id: string
  product_name: string | null
  batch_id: string | null
  batch_number: string | null
  quantity: number
  movement_type: string
  reference_type: string
  reference_id: string
  reason: string
  created_at: string
}

export type Sale = {
  id: string
  sale_number: string
  customer_id: string | null
  customer_name: string | null
  cashier_id?: string
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
  correction?: SaleCorrectionLink | null
  is_correction_of?: SaleCorrectionLink | null
  returns?: SaleReturnSummary[]
  stock_movements?: SaleMovement[]
}

export type SaleCorrection = {
  id: string
  reference: string
  sale_id: string
  sale_number: string | null
  sale_total: number | null
  sale_created_at: string | null
  sale_cashier_name: string | null
  requested_by: string
  requested_by_name: string | null
  reason: string
  status: string
  reviewed_by: string | null
  reviewed_by_name: string | null
  reviewed_at: string | null
  review_note: string
  return_id: string | null
  return_number: string | null
  refund_amount: number | null
  corrected_sale_id: string | null
  corrected_sale_number: string | null
  corrected_sale_total: number | null
  financial_difference: number | null
  created_at: string
  sale?: Sale | null
  corrected_sale?: Sale | null
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
  default_markup_percent: number | string | null
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
