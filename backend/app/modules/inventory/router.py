from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import User
from app.core.permissions import has_permission, require_permission
from app.core.responses import ForbiddenError
from app.core.schemas import BatchCreate, BatchUpdate, InventoryCounts, MovementOut, Page, ProductCreate, ProductOut, ProductUpdate, StockAdjustIn
from app.modules.inventory import service as inventory_svc

router = APIRouter(prefix="/products", tags=["inventory"])
stock_router = APIRouter(tags=["inventory"])


@router.get("", response_model=Page[ProductOut])
def list_products(
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    supplier_id: str | None = None,
    archived: bool = False,
    sort: str = "name",
    order: str = "asc",
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("inventory.read")),
):
    if archived and not has_permission(actor, "inventory.archive"):
        raise ForbiddenError()
    items, total = inventory_svc.list_products(
        db,
        q=q,
        category=category,
        status=status,
        supplier_id=supplier_id,
        archived=archived,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    return Page(items=inventory_svc.products_to_out(db, items), total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=InventoryCounts)
def product_summary(db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.status_counts(db)


@router.get("/barcode/{code}", response_model=ProductOut)
def barcode_lookup(code: str, db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.to_product_out(inventory_svc.get_by_barcode(db, code), db)


@stock_router.get("/categories", response_model=list[str])
def categories(db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.categories(db)


@router.post("", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.create"))):
    return inventory_svc.create_product(db, body, actor)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    # Include archived so historical drawers / admin archive view can still load the product.
    return inventory_svc.to_product_out(inventory_svc._get(db, product_id, include_archived=True), db)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: str, body: ProductUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.update"))):
    return inventory_svc.update_product(db, product_id, body, actor)


@router.delete("/{product_id}", response_model=ProductOut)
def deactivate_product(product_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.delete"))):
    return inventory_svc.deactivate_product(db, product_id, actor)


@router.post("/{product_id}/archive", response_model=ProductOut)
def archive_product(product_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.archive"))):
    return inventory_svc.archive_product(db, product_id, actor)


@router.post("/{product_id}/restore", response_model=ProductOut)
def restore_product(product_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.restore"))):
    return inventory_svc.restore_product(db, product_id, actor)


@router.post("/{product_id}/batches", response_model=ProductOut, status_code=201)
def add_batch(product_id: str, body: BatchCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.adjust"))):
    return inventory_svc.add_batch(db, product_id, body, actor)


@router.patch("/{product_id}/batches/{batch_id}", response_model=ProductOut)
def update_batch(
    product_id: str,
    batch_id: str,
    body: BatchUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("inventory.batch_edit")),
):
    return inventory_svc.update_batch_expiry(db, product_id, batch_id, body, actor)


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
    return Page(items=inventory_svc.movements_to_out(db, rows), total=total, limit=limit, offset=offset)
