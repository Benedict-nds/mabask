from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import User
from app.core.permissions import require_permission
from app.core.schemas import BatchCreate, InventoryCounts, MovementOut, Page, ProductCreate, ProductOut, ProductUpdate, StockAdjustIn
from app.modules.inventory import service as inventory_svc

router = APIRouter(prefix="/products", tags=["inventory"])
stock_router = APIRouter(tags=["inventory"])


@router.get("", response_model=Page[ProductOut])
def list_products(
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    supplier_id: str | None = None,
    sort: str = "name",
    order: str = "asc",
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventory.read")),
):
    items, total = inventory_svc.list_products(
        db, q=q, category=category, status=status, supplier_id=supplier_id, limit=limit, offset=offset, sort=sort, order=order
    )
    return Page(items=[inventory_svc.to_product_out(p) for p in items], total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=InventoryCounts)
def product_summary(db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.status_counts(db)


@router.get("/barcode/{code}", response_model=ProductOut)
def barcode_lookup(code: str, db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.to_product_out(inventory_svc.get_by_barcode(db, code))


@stock_router.get("/categories", response_model=list[str])
def categories(db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.categories(db)


@router.post("", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.create"))):
    return inventory_svc.create_product(db, body, actor)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.to_product_out(inventory_svc._get(db, product_id))


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: str, body: ProductUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.update"))):
    return inventory_svc.update_product(db, product_id, body, actor)


@router.delete("/{product_id}", response_model=ProductOut)
def deactivate_product(product_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.delete"))):
    return inventory_svc.deactivate_product(db, product_id, actor)


@router.post("/{product_id}/batches", response_model=ProductOut, status_code=201)
def add_batch(product_id: str, body: BatchCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.adjust"))):
    return inventory_svc.add_batch(db, product_id, body, actor)


@router.post("/{product_id}/adjust", response_model=ProductOut)
def adjust(product_id: str, body: StockAdjustIn, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.adjust"))):
    return inventory_svc.adjust_stock(db, product_id, body, actor)


@stock_router.get("/stock-movements", response_model=Page[MovementOut])
def movements(
    product_id: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventory.read")),
):
    rows, total = inventory_svc.list_movements(db, product_id, limit, offset)
    items = [
        MovementOut(
            id=m.id,
            product_id=m.product_id,
            product_name=m.product.name if m.product else None,
            batch_id=m.batch_id,
            quantity=m.quantity,
            previous_quantity=m.previous_quantity,
            resulting_quantity=m.resulting_quantity,
            movement_type=m.movement_type.value,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            reason=m.reason,
            created_at=m.created_at,
            user_id=m.user_id,
        )
        for m in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
