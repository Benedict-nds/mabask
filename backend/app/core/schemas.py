from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

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


class RoleOut(BaseModel):
    name: str
    description: str
    permissions: list[str]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: str
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class ProductCreate(BaseModel):
    sku: str
    barcode: str
    name: str
    generic_name: str = ""
    brand: str = ""
    category: str
    description: str = ""
    dosage_form: str = ""
    strength: str = ""
    unit: str = "tablet"
    cost_price: Decimal = Decimal("0")
    selling_price: Decimal
    reorder_threshold: int = 0
    supplier_id: str | None = None
    is_active: bool = True
    initial_quantity: int = 0
    batch_number: str = ""
    expiry_date: OptionalExpiry = None


class ProductUpdate(BaseModel):
    sku: str | None = None
    barcode: str | None = None
    name: str | None = None
    generic_name: str | None = None
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    dosage_form: str | None = None
    strength: str | None = None
    unit: str | None = None
    cost_price: Decimal | None = None
    selling_price: Decimal | None = None
    reorder_threshold: int | None = None
    supplier_id: str | None = None
    is_active: bool | None = None


class InventoryCounts(BaseModel):
    total: int
    healthy: int
    low: int
    critical: int


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_number: str
    expiry_date: Expiry
    quantity: int
    cost_price: Decimal


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
    subtotal: Decimal
    total: Decimal
    created_by: str
    approved_by: str | None
    created_at: datetime
    items: list[POItemOut] = []


class ReceiveLineIn(BaseModel):
    item_id: str
    quantity: int = Field(gt=0)
    batch_number: str | None = None
    expiry_date: OptionalExpiry = None
    unit_cost: Decimal | None = None


class ReceiveIn(BaseModel):
    lines: list[ReceiveLineIn]


class ExtractedLine(BaseModel):
    name: str
    quantity: int
    unit_cost: Decimal
    batch: str = ""
    expiry: OptionalExpiry = None
    confidence: float
    matched: bool
    product_id: str | None = None


class ExtractOut(BaseModel):
    supplier_id: str | None = None
    supplier_name: str | None = None
    items: list[ExtractedLine]


class ImportReceiveIn(BaseModel):
    supplier_id: str
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
    barcode: str | None = None
    quantity: int
    quantity_returned: int
    unit_price: Decimal
    line_total: Decimal
    returnable: int = 0


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


class SettingsUpdate(BaseModel):
    pharmacy_name: str | None = None
    license_number: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    tax_rate: Decimal | None = None


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
