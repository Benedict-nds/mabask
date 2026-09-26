from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class RoleName(str, enum.Enum):
    ADMIN = "admin"
    PHARMACIST = "pharmacist"
    CASHIER = "cashier"


class SupplierStatus(str, enum.Enum):
    PREFERRED = "preferred"
    ACTIVE = "active"
    REVIEW = "review"
    INACTIVE = "inactive"


class POStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class MovementType(str, enum.Enum):
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    RETURN = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    DAMAGE = "DAMAGE"
    EXPIRY = "EXPIRY"
    TRANSFER = "TRANSFER"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    MOBILE_MONEY = "MOBILE_MONEY"
    OTHER = "OTHER"


class SaleStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class CorrectionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")

    users: Mapped[list[User]] = relationship(back_populates="role")
    permissions: Mapped[list[RolePermission]] = relationship(back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")

    roles: Mapped[list[RolePermission]] = relationship(back_populates="permission")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)

    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship(back_populates="roles")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped[Role] = relationship(back_populates="users")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user", cascade="all, delete-orphan")
    permission_overrides: Mapped[list[UserPermissionOverride]] = relationship(
        foreign_keys="UserPermissionOverride.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PermissionEffect(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class UserPermissionOverride(TimestampMixin, Base):
    """Per-user exception to the role baseline. No row means INHERIT."""

    __tablename__ = "user_permission_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "permission_code", name="uq_user_permission_override"),
        CheckConstraint("effect IN ('ALLOW', 'DENY')", name="ck_user_permission_override_effect"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_code: Mapped[str] = mapped_column(String(64), nullable=False)
    effect: Mapped[str] = mapped_column(String(8), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    user: Mapped[User] = relationship(foreign_keys=[user_id], back_populates="permission_overrides")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[SupplierStatus] = mapped_column(Enum(SupplierStatus), default=SupplierStatus.ACTIVE, nullable=False)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 1), default=Decimal("0.0"))
    on_time_rate: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    products: Mapped[list[Product]] = relationship(back_populates="supplier")
    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="supplier")


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_products_sku"),
        UniqueConstraint("barcode", name="uq_products_barcode"),
        CheckConstraint("selling_price >= 0", name="ck_products_selling_price"),
        CheckConstraint("cost_price >= 0", name="ck_products_cost_price"),
        CheckConstraint("quantity_on_hand >= 0", name="ck_products_qty"),
        CheckConstraint("reorder_threshold >= 0", name="ck_products_reorder"),
        Index("ix_products_name", "name"),
        Index("ix_products_category", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # Optional: supplier invoices carry neither. NULL (never "") keeps the unique constraints usable.
    sku: Mapped[str | None] = mapped_column(String(40), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    generic_name: Mapped[str] = mapped_column(String(200), default="")
    brand: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="General")
    description: Mapped[str] = mapped_column(Text, default="")
    dosage_form: Mapped[str] = mapped_column(String(80), default="")
    strength: Mapped[str] = mapped_column(String(80), default="")
    unit: Mapped[str] = mapped_column(String(40), default="tablet")
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    supplier: Mapped[Supplier | None] = relationship(back_populates="products")
    batches: Mapped[list[Batch]] = relationship(back_populates="product", cascade="all, delete-orphan")
    movements: Mapped[list[StockMovement]] = relationship(back_populates="product")


class Batch(TimestampMixin, Base):
    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("product_id", "batch_number", name="uq_batch_product_number"),
        CheckConstraint("quantity >= 0", name="ck_batches_qty"),
        Index("ix_batches_expiry", "expiry_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(64), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped[Product] = relationship(back_populates="batches")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_stock_movements_product_created", "product_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(40), default="")
    reference_id: Mapped[str] = mapped_column(String(36), default="")
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product: Mapped[Product] = relationship(back_populates="movements")
    batch: Mapped[Batch | None] = relationship()
    user: Mapped[User | None] = relationship()


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    po_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    status: Mapped[POStatus] = mapped_column(Enum(POStatus), default=POStatus.DRAFT, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    review_requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    supplier: Mapped[Supplier] = relationship(back_populates="purchase_orders")
    items: Mapped[list[PurchaseOrderItem]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[review_requested_by])


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (CheckConstraint("quantity_ordered > 0", name="ck_poi_qty_ordered"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(64), default="")
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_name", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sales: Mapped[list[Sale]] = relationship(back_populates="customer")


class Sale(TimestampMixin, Base):
    __tablename__ = "sales"
    __table_args__ = (
        UniqueConstraint("sale_number", name="uq_sales_number"),
        UniqueConstraint("idempotency_key", name="uq_sales_idempotency"),
        CheckConstraint("total >= 0", name="ck_sales_total"),
        Index("ix_sales_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sale_number: Mapped[str] = mapped_column(String(40), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    cashier_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[SaleStatus] = mapped_column(Enum(SaleStatus), default=SaleStatus.COMPLETED, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    amount_tendered: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    change_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str] = mapped_column(String(255), default="")

    customer: Mapped[Customer | None] = relationship(back_populates="sales")
    cashier: Mapped[User] = relationship()
    items: Mapped[list[SaleItem]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    returns: Mapped[list[Return]] = relationship(back_populates="sale")


class SaleItem(Base):
    __tablename__ = "sale_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_sale_items_qty"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()
    batch: Mapped[Batch | None] = relationship()


class Return(TimestampMixin, Base):
    __tablename__ = "returns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    return_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id"), nullable=False)
    cashier_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    restock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="returns")
    cashier: Mapped[User] = relationship()
    items: Mapped[list[ReturnItem]] = relationship(back_populates="return_record", cascade="all, delete-orphan")


class ReturnItem(Base):
    __tablename__ = "return_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    return_id: Mapped[str] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"), nullable=False)
    sale_item_id: Mapped[str] = mapped_column(ForeignKey("sale_items.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    return_record: Mapped[Return] = relationship(back_populates="items")
    sale_item: Mapped[SaleItem] = relationship()
    product: Mapped[Product] = relationship()


class SaleCorrectionRequest(TimestampMixin, Base):
    """Admin-reviewed correction for a wrong sale. Original sale is never edited in place."""

    __tablename__ = "sale_correction_requests"
    __table_args__ = (Index("ix_sale_corrections_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id"), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CorrectionStatus] = mapped_column(
        Enum(CorrectionStatus), default=CorrectionStatus.PENDING, nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    return_id: Mapped[str | None] = mapped_column(ForeignKey("returns.id"), nullable=True)
    corrected_sale_id: Mapped[str | None] = mapped_column(ForeignKey("sales.id"), nullable=True)
    approval_idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    sale: Mapped[Sale] = relationship(foreign_keys=[sale_id])
    requester: Mapped[User] = relationship(foreign_keys=[requested_by])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])
    return_record: Mapped[Return | None] = relationship(foreign_keys=[return_id])
    corrected_sale: Mapped[Sale | None] = relationship(foreign_keys=[corrected_sale_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_created", "created_at"), Index("ix_audit_entity", "entity_type", "entity_id"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), default="")
    details: Mapped[str] = mapped_column(Text, default="{}")
    # Python-side default keeps sub-second ordering on SQLite, whose now() only has second resolution.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User | None] = relationship()


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
