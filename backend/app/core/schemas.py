from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BeforeValidator, BaseModel, ConfigDict, EmailStr, Field

from app.core.dates import parse_expiry


def _as_expiry(value: object) -> date:
    parsed = parse_expiry(value, required=True)
    assert parsed is not None
    return parsed


def _as_optional_expiry(value: object) -> date | None:
    return parse_expiry(value, required=False)


Expiry = Annotated[date, BeforeValidator(_as_expiry)]
OptionalExpiry = Annotated[date | None, BeforeValidator(_as_optional_expiry)]

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    permissions: list[str]
    is_active: bool
    last_login_at: datetime | None = None
    permission_overrides: dict[str, str] = {}


class RoleOut(BaseModel):
    name: str
    description: str
    permissions: list[str]


OverrideState = Literal["INHERIT", "ALLOW", "DENY"]


class PermissionInfo(BaseModel):
    code: str
    description: str
    group: str
    group_label: str
    admin_only: bool


class UserPermissionEntry(PermissionInfo):
    role_default: bool
    override: OverrideState
    effective: bool
    locked: bool
    locked_reason: str | None = None


class UserPermissionsOut(BaseModel):
    user_id: str
    full_name: str
    role: str
    editable: bool
    not_editable_reason: str | None = None
    override_count: int
    permissions: list[UserPermissionEntry]


class PermissionOverridesUpdate(BaseModel):
    overrides: dict[str, OverrideState] = Field(min_length=1)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: str
    is_active: bool = True
    permission_overrides: dict[str, OverrideState] = {}


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class ProductCreate(BaseModel):
    """Required: name, cost_price, selling_price, reorder_threshold. Everything else is optional."""

    sku: str | None = Field(default=None, max_length=40)
    barcode: str | None = Field(default=None, max_length=64)
    name: str = Field(max_length=200)
    generic_name: str = ""
    brand: str = ""
    category: str = "General"
    description: str = ""
    dosage_form: str = ""
    strength: str = ""
    unit: str = "tablet"
    cost_price: Decimal = Field(ge=0)
    selling_price: Decimal = Field(ge=0)
    reorder_threshold: int = Field(ge=0)
    supplier_id: str | None = None
    is_active: bool = True
    initial_quantity: int = 0
    batch_number: str = ""
    expiry_date: OptionalExpiry = None


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, max_length=40)
    barcode: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    generic_name: str | None = None
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    dosage_form: str | None = None
    strength: str | None = None
    unit: str | None = None
    cost_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    reorder_threshold: int | None = Field(default=None, ge=0)
    supplier_id: str | None = None
    is_active: bool | None = None


class InventoryCounts(BaseModel):
    total: int
    healthy: int
    low: int
    critical: int


class BatchSupplierOut(BaseModel):
    id: str
    name: str


class BatchPurchaseOrderOut(BaseModel):
    id: str
    po_number: str


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_number: str
    expiry_date: Expiry
    quantity: int
    cost_price: Decimal
    supplier: BatchSupplierOut | None = None
    purchase_order: BatchPurchaseOrderOut | None = None
    received_at: datetime | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sku: str
    barcode: str
    name: str
    generic_name: str
    brand: str
    category: str
    description: str
    dosage_form: str
    strength: str
    unit: str
    cost_price: Decimal
    selling_price: Decimal
    quantity_on_hand: int
    reorder_threshold: int
    supplier_id: str | None
    supplier_name: str | None = None
    is_active: bool
    deleted_at: datetime | None = None
    status: str
    nearest_expiry: OptionalExpiry = None
    nearest_batch: str | None = None
    batches: list[BatchOut] = []


class BatchCreate(BaseModel):
    batch_number: str
    expiry_date: Expiry
    quantity: int = Field(ge=0)
    cost_price: Decimal | None = None


class StockAdjustIn(BaseModel):
    quantity_delta: int
    reason: str
    movement_type: str = "ADJUSTMENT"
    batch_id: str | None = None


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    product_name: str | None = None
    batch_id: str | None
    quantity: int
    previous_quantity: int
    resulting_quantity: int
    movement_type: str
    reference_type: str
    reference_id: str
    reason: str
    created_at: datetime
    user_id: str | None
    po_number: str | None = None
    supplier_id: str | None = None
    supplier_name: str | None = None


class SupplierCreate(BaseModel):
    name: str
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    status: str = "active"
    rating: Decimal = Decimal("0")
    on_time_rate: int = 0
    notes: str = ""


class SupplierUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    status: str | None = None
    rating: Decimal | None = None
    on_time_rate: int | None = None
    notes: str | None = None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    contact_name: str
    email: str
    phone: str
    address: str
    status: str
    rating: Decimal
    on_time_rate: int
    notes: str
    active_skus: int = 0
    outstanding: Decimal = Decimal("0")
    last_delivery: date | None = None


class POItemIn(BaseModel):
    product_id: str | None = None
    product_name: str
    quantity_ordered: int = Field(gt=0)
    unit_cost: Decimal
    batch_number: str = ""
    expiry_date: OptionalExpiry = None


class POCreate(BaseModel):
    supplier_id: str
    notes: str = ""
    items: list[POItemIn]


class POReviewEditIn(POCreate):
    """Reviewer edit of a SUBMITTED PO. The reason is audited so edits are never silent."""

    reason: str = Field(min_length=1, max_length=500)


class POItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str | None
    product_name: str
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal
    batch_number: str
    expiry_date: OptionalExpiry


class POOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    po_number: str
    supplier_id: str
    supplier_name: str | None = None
    status: str
    notes: str
    review_comment: str = ""
    review_requested_by: str | None = None
    review_requested_by_name: str | None = None
    review_requested_at: datetime | None = None
    subtotal: Decimal
    total: Decimal
    created_by: str
    created_by_name: str | None = None
    approved_by: str | None
    created_at: datetime
    items: list[POItemOut] = []


class RequestChangesIn(BaseModel):
    reason: str


class ReceiveLineIn(BaseModel):
    item_id: str
    quantity: int = Field(gt=0)
    batch_number: str | None = None
    expiry_date: OptionalExpiry = None
    unit_cost: Decimal | None = None
    notes: str = Field(default="", max_length=200)


class ReceiveIn(BaseModel):
    lines: list[ReceiveLineIn]


class AdhocReceiveLineIn(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    batch_number: str = ""
    expiry_date: OptionalExpiry = None
    notes: str = Field(default="", max_length=200)


class AdhocReceiveIn(BaseModel):
    """Multi-line receipt without a prior PO. Supplier is optional and never invented."""

    supplier_id: str | None = None
    notes: str = Field(default="", max_length=500)
    items: list[AdhocReceiveLineIn]


class ReceiptLineOut(BaseModel):
    product_id: str
    product_name: str
    batch_id: str
    batch_number: str
    expiry_date: date
    quantity: int
    unit_cost: Decimal


class ReceiptOut(BaseModel):
    reference: str
    receipt_id: str | None = None
    purchase_order_id: str | None = None
    po_number: str | None = None
    supplier_id: str | None = None
    supplier_name: str | None = None
    units_received: int
    lines: list[ReceiptLineOut]


class ExtractedLine(BaseModel):
    name: str
    quantity: int
    unit_cost: Decimal
    batch: str = ""
    expiry: OptionalExpiry = None
    confidence: float
    matched: bool
    product_id: str | None = None
    row: int | None = None
    description: str = ""
    discount: Decimal | None = None
    amount: Decimal | None = None
    selling_price: Decimal | None = None
    expiry_raw: str = ""
    issues: list[str] = []
    product_sku: str = ""
    current_cost_price: Decimal | None = None
    current_selling_price: Decimal | None = None
    archived_product_id: str | None = None
    archived_product_name: str | None = None


class SkippedRowOut(BaseModel):
    row: int
    reason: str
    text: str


class ExtractOut(BaseModel):
    supplier_id: str | None = None
    supplier_name: str | None = None
    items: list[ExtractedLine]
    source: Literal["csv", "ai"] = "csv"
    columns: dict[str, str] = {}
    ignored_columns: list[str] = []
    discount_mode: Literal["percent", "amount"] = "percent"
    discount_mode_source: str = ""
    skipped_rows: list[SkippedRowOut] = []
    default_markup_percent: Decimal | None = None


class InvoiceNewProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    reorder_threshold: int = Field(default=0, ge=0)


class InvoiceLineIn(BaseModel):
    row: int | None = None
    description: str = Field(default="", max_length=300)
    product_id: str | None = None
    new_product: InvoiceNewProductIn | None = None
    quantity: int = Field(gt=0)
    rate: Decimal = Field(ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    amount: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    batch_number: str = Field(default="", max_length=64)
    expiry_date: OptionalExpiry = None


class InvoiceImportIn(BaseModel):
    """Confirm a reviewed supplier invoice. Rate is the unit cost; selling price comes from an
    explicit per-line price, else cost x (1 + markup_percent/100)."""

    supplier_id: str | None = None
    notes: str = Field(default="", max_length=500)
    source: str = Field(default="CSV invoice", max_length=60)
    markup_percent: Decimal | None = Field(default=None, ge=0, le=1000)
    discount_mode: Literal["percent", "amount"] = "percent"
    update_existing_prices: bool = False
    items: list[InvoiceLineIn]


class InvoicePriceOut(BaseModel):
    product_id: str
    product_name: str
    cost_price: Decimal
    old_selling_price: Decimal | None = None
    new_selling_price: Decimal
    price_source: Literal["explicit", "markup"]


class InvoiceImportOut(BaseModel):
    receipt: ReceiptOut
    markup_percent: Decimal | None = None
    discount_mode: Literal["percent", "amount"]
    invoice_total: Decimal
    created_products: list[InvoicePriceOut] = []
    price_updates: list[InvoicePriceOut] = []


class ImportReceiveIn(BaseModel):
    supplier_id: str
    notes: str = "Invoice import"
    items: list[POItemIn]


class SaleItemIn(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class SaleCreate(BaseModel):
    items: list[SaleItemIn]
    payment_method: str
    amount_tendered: Decimal | None = None
    discount_percent: Decimal = Decimal("0")
    tax_rate: Decimal | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    idempotency_key: str
    notes: str = ""


class SaleItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    product_name: str | None = None
    product_sku: str | None = None
    barcode: str | None = None
    batch_id: str | None = None
    batch_number: str | None = None
    batch_expiry: OptionalExpiry = None
    batch_cost_price: Decimal | None = None
    batch_supplier_id: str | None = None
    batch_supplier_name: str | None = None
    batch_po_id: str | None = None
    batch_po_number: str | None = None
    quantity: int
    quantity_returned: int
    unit_price: Decimal
    line_total: Decimal
    returnable: int = 0


class SaleCorrectionLinkOut(BaseModel):
    """Lightweight correction linkage for sales journals."""

    request_id: str
    reference: str = ""
    status: str
    corrected_sale_id: str | None = None
    corrected_sale_number: str | None = None
    original_sale_id: str | None = None
    original_sale_number: str | None = None
    financial_difference: Decimal | None = None
    return_id: str | None = None
    return_number: str | None = None
    refund_amount: Decimal | None = None
    reason: str | None = None
    requested_by_name: str | None = None
    requested_at: datetime | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None


class SaleReturnItemOut(BaseModel):
    product_id: str
    product_name: str | None = None
    quantity: int
    unit_price: Decimal


class SaleReturnSummaryOut(BaseModel):
    id: str
    return_number: str
    reason: str
    refund_amount: Decimal
    restock: bool
    created_at: datetime
    processed_by_name: str | None = None
    items: list[SaleReturnItemOut] = []


class SaleMovementOut(BaseModel):
    id: str
    product_id: str
    product_name: str | None = None
    batch_id: str | None = None
    batch_number: str | None = None
    quantity: int
    movement_type: str
    reference_type: str
    reference_id: str
    reason: str
    created_at: datetime


class SaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sale_number: str
    customer_id: str | None
    customer_name: str | None = None
    cashier_id: str
    cashier_name: str | None = None
    status: str
    subtotal: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal
    payment_method: str
    amount_tendered: Decimal
    change_due: Decimal
    created_at: datetime
    items: list[SaleItemOut] = []
    correction: SaleCorrectionLinkOut | None = None
    is_correction_of: SaleCorrectionLinkOut | None = None
    returns: list[SaleReturnSummaryOut] = []
    stock_movements: list[SaleMovementOut] = []


class ReturnItemIn(BaseModel):
    sale_item_id: str
    quantity: int = Field(gt=0)


class ReturnCreate(BaseModel):
    sale_id: str
    reason: str
    restock: bool = True
    items: list[ReturnItemIn]


class ReturnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    return_number: str
    sale_id: str
    reason: str
    refund_amount: Decimal
    restock: bool
    created_at: datetime


class CorrectionRequestIn(BaseModel):
    reason: str


class CorrectionRejectIn(BaseModel):
    reason: str


class CorrectionApproveIn(BaseModel):
    """Admin-specified corrected cart. Same money fields as SaleCreate."""

    items: list[SaleItemIn]
    payment_method: str
    amount_tendered: Decimal | None = None
    discount_percent: Decimal = Decimal("0")
    tax_rate: Decimal | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    notes: str = ""
    review_note: str = ""
    idempotency_key: str


class CorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str = ""
    sale_id: str
    sale_number: str | None = None
    sale_total: Decimal | None = None
    sale_created_at: datetime | None = None
    sale_cashier_name: str | None = None
    requested_by: str
    requested_by_name: str | None = None
    reason: str
    status: str
    reviewed_by: str | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str = ""
    return_id: str | None = None
    return_number: str | None = None
    refund_amount: Decimal | None = None
    corrected_sale_id: str | None = None
    corrected_sale_number: str | None = None
    corrected_sale_total: Decimal | None = None
    financial_difference: Decimal | None = None
    created_at: datetime
    sale: SaleOut | None = None
    corrected_sale: SaleOut | None = None


class CustomerCreate(BaseModel):
    name: str
    phone: str = ""
    email: str = ""
    notes: str = ""


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    phone: str
    email: str
    notes: str


class SettingsOut(BaseModel):
    pharmacy_name: str
    license_number: str
    phone: str
    email: str
    address: str
    tax_rate: Decimal
    currency: str = "GHS"
    default_markup_percent: Decimal | None = None


class SettingsUpdate(BaseModel):
    pharmacy_name: str | None = None
    license_number: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    tax_rate: Decimal | None = None
    default_markup_percent: Decimal | None = Field(default=None, ge=0, le=1000)


class CopilotAsk(BaseModel):
    question: str


class CopilotAnswer(BaseModel):
    text: str
    table: dict[str, Any] | None = None
    actions: list[str] = []
    followups: list[str] = []
    source: str
    llm_used: bool = False


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    message: str
    kind: str
    is_read: bool
    created_at: datetime


class AuditOut(BaseModel):
    id: str
    user_id: str | None
    actor: str | None = None
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    created_at: datetime
