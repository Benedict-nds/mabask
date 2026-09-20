from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.permissions import require_permission
from app.core.schemas import ProductOut
from app.models import User
from app.modules.inventory import service as inventory_svc

router = APIRouter(prefix="/products", tags=["barcode"])


@router.get("/barcode/{code}", response_model=ProductOut)
def barcode_lookup(code: str, db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    return inventory_svc.to_product_out(inventory_svc.get_by_barcode(db, code))
