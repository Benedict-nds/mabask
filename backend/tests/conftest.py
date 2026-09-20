import os
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-for-jwt-tokens"
os.environ["CORS_ORIGINS"] = "http://test"
os.environ["ENVIRONMENT"] = "test"
os.environ["AI_PROVIDER"] = ""
os.environ["AI_API_KEY"] = ""
os.environ["AETHERQORE_ENV_FILE"] = os.path.join(os.path.dirname(__file__), ".env.does-not-exist")

from app.core.config import get_settings

get_settings.cache_clear()

from app.core.db import Base, get_db
from app.main import app
from app.models import Batch, MovementType, Product, Role, Supplier, SupplierStatus, User
from app.core.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS
from app.models import Permission, RolePermission
from app.core.security import hash_password
from app.modules.inventory.stock import apply_stock_change
from seed import seed_rbac

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=True)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    roles = seed_rbac(session)
    admin = User(
        email="amara@brightcare.pharmacy",
        password_hash=hash_password("pharmacy123"),
        full_name="Amara Kane",
        role_id=roles["admin"].id,
    )
    cashier = User(
        email="lena@brightcare.pharmacy",
        password_hash=hash_password("pharmacy123"),
        full_name="Lena Ross",
        role_id=roles["cashier"].id,
    )
    pharmacist = User(
        email="grace@brightcare.pharmacy",
        password_hash=hash_password("pharmacy123"),
        full_name="Grace Mensah",
        role_id=roles["pharmacist"].id,
    )
    session.add_all([admin, cashier, pharmacist])
    supplier = Supplier(name="MediSource Global", contact_name="Elena", email="orders@medisource.com", status=SupplierStatus.PREFERRED)
    session.add(supplier)
    session.flush()
    product = Product(
        sku="MD-1001",
        barcode="8901234500011",
        name="Amoxicillin 500mg",
        brand="Amoxil",
        category="Antibiotics",
        cost_price=Decimal("0.18"),
        selling_price=Decimal("0.35"),
        reorder_threshold=400,
        supplier_id=supplier.id,
        quantity_on_hand=0,
    )
    session.add(product)
    session.flush()
    batch = Batch(product_id=product.id, batch_number="AMX-2231", expiry_date=date(2027, 4, 1), quantity=0, cost_price=Decimal("0.18"))
    session.add(batch)
    session.flush()
    apply_stock_change(
        session,
        product=product,
        delta=100,
        movement_type=MovementType.PURCHASE,
        user=admin,
        batch=batch,
        reason="test stock",
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers(client: TestClient, email: str = "amara@brightcare.pharmacy") -> dict:
    res = client.post("/auth/login", json={"email": email, "password": "pharmacy123"})
    assert res.status_code == 200, res.text
    token = res.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
