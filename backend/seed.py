"""Load realistic BrightCare Pharmacy development data."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.dates import parse_expiry
from app.core.db import Base
from app.models import (
    Batch,
    Customer,
    MovementType,
    Permission,
    Product,
    Role,
    RolePermission,
    PaymentMethod,
    Sale,
    SaleItem,
    Setting,
    Supplier,
    SupplierStatus,
    User,
)
from app.core.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS
from app.core.security import hash_password
from app.modules.inventory.stock import apply_stock_change

MEDICINES = [
    ("MD-1001", "8901234500011", "Amoxicillin 500mg", "Amoxicillin", "Amoxil", "Antibiotics", "capsule", "500mg", 0.18, 0.35, 400, "AMX-2231", date(2026, 12, 14), 1240),
    ("MD-1002", "8901234500028", "Paracetamol 500mg", "Paracetamol", "Panadol", "Analgesics", "tablet", "500mg", 0.05, 0.12, 800, "PCM-9910", date(2027, 1, 9), 3820),
    ("MD-1003", "8901234500035", "Atorvastatin 20mg", "Atorvastatin", "Lipitor", "Cardiovascular", "tablet", "20mg", 0.31, 0.62, 300, "ATV-4420", date(2026, 11, 22), 210),
    ("MD-1004", "8901234500042", "Metformin 850mg", "Metformin", "Glucophage", "Antidiabetic", "tablet", "850mg", 0.14, 0.28, 350, "MET-1180", date(2026, 10, 30), 90),
    ("MD-1005", "8901234500059", "Salbutamol Inhaler", "Salbutamol", "Ventolin", "Respiratory", "inhaler", "100mcg", 2.60, 4.90, 120, "SAL-7712", date(2026, 10, 11), 64),
    ("MD-1006", "8901234500066", "Vitamin D3 1000IU", "Cholecalciferol", "Cavit-D", "Vitamins", "capsule", "1000IU", 0.09, 0.22, 500, "VTD-3391", date(2027, 6, 18), 1560),
    ("MD-1007", "8901234500073", "Omeprazole 20mg", "Omeprazole", "Losec", "Gastrointestinal", "capsule", "20mg", 0.20, 0.44, 300, "OMP-2205", date(2026, 11, 4), 720),
    ("MD-1008", "8901234500080", "Azithromycin 250mg", "Azithromycin", "Zithromax", "Antibiotics", "tablet", "250mg", 0.50, 0.95, 150, "AZM-6640", date(2026, 10, 8), 38),
    ("MD-1009", "8901234500097", "Ibuprofen 400mg", "Ibuprofen", "Brufen", "Analgesics", "tablet", "400mg", 0.07, 0.18, 600, "IBU-8123", date(2027, 3, 1), 2450),
    ("MD-1010", "8901234500103", "Losartan 50mg", "Losartan", "Cozaar", "Cardiovascular", "tablet", "50mg", 0.24, 0.50, 250, "LOS-4409", date(2026, 12, 19), 480),
    ("MD-1011", "8901234500110", "Cetirizine 10mg", "Cetirizine", "Zyrtec", "Respiratory", "tablet", "10mg", 0.06, 0.15, 300, "CET-1902", date(2027, 7, 25), 990),
    ("MD-1012", "8901234500127", "Insulin Glargine", "Insulin glargine", "Lantus", "Antidiabetic", "vial", "100IU/ml", 11.20, 18.50, 80, "INS-3320", date(2026, 10, 20), 52),
    ("MD-1013", "8901234500134", "Hydrocortisone Cream", "Hydrocortisone", "Cortaid", "Dermatology", "tube", "1%", 1.05, 2.10, 150, "HYD-5561", date(2027, 2, 14), 340),
    ("MD-1014", "8901234500141", "Amlodipine 5mg", "Amlodipine", "Norvasc", "Cardiovascular", "tablet", "5mg", 0.15, 0.33, 250, "AML-7788", date(2026, 11, 6), 175),
    ("MD-1015", "8901234500158", "Multivitamin Complex", "Multivitamin", "Centrum", "Vitamins", "tablet", "", 0.18, 0.40, 700, "MVC-2010", date(2027, 9, 12), 2100),
]


def seed_rbac(db: Session) -> dict[str, Role]:
    perms: dict[str, Permission] = {}
    for code, desc in ALL_PERMISSIONS:
        row = db.query(Permission).filter(Permission.code == code).first()
        if row is None:
            row = Permission(code=code, description=desc)
            db.add(row)
            db.flush()
        perms[code] = row

    roles: dict[str, Role] = {}
    for name, codes in ROLE_PERMISSIONS.items():
        role = db.query(Role).filter(Role.name == name).first()
        if role is None:
            role = Role(name=name, description=name.title())
            db.add(role)
            db.flush()
        existing = {
            rp.permission_id
            for rp in db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
        }
        for code in codes:
            if perms[code].id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=perms[code].id))
        roles[name] = role
    db.flush()
    return roles


def seed_users(db: Session, roles: dict[str, Role]) -> dict[str, User]:
    specs = [
        ("amara@brightcare.pharmacy", "Amara Kane", "admin"),
        ("grace@brightcare.pharmacy", "Grace Thompson", "pharmacist"),
        ("daniel@brightcare.pharmacy", "Daniel Kim", "pharmacist"),
        ("lena@brightcare.pharmacy", "Lena Ross", "cashier"),
    ]
    users = {}
    for email, name, role_name in specs:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password("pharmacy123"),
                full_name=name,
                role_id=roles[role_name].id,
            )
            db.add(user)
            db.flush()
        users[email] = user
    return users


def seed_settings(db: Session) -> None:
    values = {
        "pharmacy_name": "BrightCare Pharmacy",
        "license_number": "RX-2026-88214",
        "phone": "+1 (555) 019-4477",
        "email": "hello@brightcare.pharmacy",
        "address": "240 Meridian Ave, Suite 12",
        "tax_rate": "5",
        "currency": "GHS",
    }
    for key, value in values.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=value))


def run(db: Session) -> None:
    roles = seed_rbac(db)
    users = seed_users(db, roles)
    seed_settings(db)
    actor = users["amara@brightcare.pharmacy"]

    suppliers_spec = [
        ("MediSource Global", "Elena Marsh", "orders@medisource.com", SupplierStatus.PREFERRED, Decimal("4.8"), 97),
        ("PharmaTrust Ltd", "David Okoye", "supply@pharmatrust.io", SupplierStatus.ACTIVE, Decimal("4.5"), 92),
        ("Nova Health Dist.", "Priya Nair", "hello@novahealth.co", SupplierStatus.REVIEW, Decimal("4.1"), 84),
        ("Zenith Pharma Co.", "Marco Silva", "sales@zenithpharma.com", SupplierStatus.ACTIVE, Decimal("4.6"), 95),
    ]
    suppliers: dict[str, Supplier] = {}
    for name, contact, email, status, rating, on_time in suppliers_spec:
        row = db.query(Supplier).filter(Supplier.name == name).first()
        if row is None:
            row = Supplier(name=name, contact_name=contact, email=email, status=status, rating=rating, on_time_rate=on_time)
            db.add(row)
            db.flush()
        suppliers[name] = row

    supplier_for = {
        "Antibiotics": "MediSource Global",
        "Analgesics": "PharmaTrust Ltd",
        "Cardiovascular": "MediSource Global",
        "Antidiabetic": "Nova Health Dist.",
        "Respiratory": "PharmaTrust Ltd",
        "Vitamins": "Nova Health Dist.",
        "Dermatology": "MediSource Global",
        "Gastrointestinal": "MediSource Global",
    }

    products = {}
    for row in MEDICINES:
        sku, barcode, name, generic, brand, category, form, strength, cost, price, reorder, batch_no, expiry, qty = row
        product = db.query(Product).filter(Product.sku == sku).first()
        if product is None:
            product = Product(
                sku=sku,
                barcode=barcode,
                name=name,
                generic_name=generic,
                brand=brand,
                category=category,
                dosage_form=form,
                strength=strength,
                unit=form,
                cost_price=Decimal(str(cost)),
                selling_price=Decimal(str(price)),
                reorder_threshold=reorder,
                supplier_id=suppliers[supplier_for[category]].id,
                quantity_on_hand=0,
            )
            db.add(product)
            db.flush()
            batch = Batch(
                product_id=product.id,
                batch_number=batch_no,
                expiry_date=parse_expiry(expiry, required=True),
                quantity=0,
                cost_price=Decimal(str(cost)),
            )
            db.add(batch)
            db.flush()
            apply_stock_change(
                db,
                product=product,
                delta=qty,
                movement_type=MovementType.PURCHASE,
                user=actor,
                batch=batch,
                reference_type="seed",
                reference_id=product.id,
                reason="Opening stock",
            )
        products[sku] = product

    if db.query(Customer).count() == 0:
        db.add(Customer(name="Walk-in", notes="Default counter customer"))
        db.add(Customer(name="Kwame Mensah", phone="+233 24 555 0190"))

    if db.query(Sale).count() == 0:
        para = products["MD-1002"]
        sale = Sale(
            sale_number="SALE-2026-0001",
            cashier_id=users["lena@brightcare.pharmacy"].id,
            subtotal=Decimal("0.24"),
            discount_percent=Decimal("0"),
            discount_amount=Decimal("0"),
            tax_rate=Decimal("5"),
            tax_amount=Decimal("0.01"),
            total=Decimal("0.25"),
            payment_method=PaymentMethod.CASH,
            amount_tendered=Decimal("1.00"),
            change_due=Decimal("0.75"),
            idempotency_key="seed-sale-1",
        )
        db.add(sale)
        db.flush()
        batch = para.batches[0]
        apply_stock_change(
            db,
            product=para,
            delta=-2,
            movement_type=MovementType.SALE,
            user=users["lena@brightcare.pharmacy"],
            batch=batch,
            reference_type="sale",
            reference_id=sale.id,
            reason="Seed sale",
        )
        db.add(
            SaleItem(
                sale_id=sale.id,
                product_id=para.id,
                batch_id=batch.id,
                quantity=2,
                unit_price=para.selling_price,
                line_total=Decimal("0.24"),
            )
        )

    db.commit()
    print("Seed complete.")
    print("  Admin:      amara@brightcare.pharmacy / pharmacy123")
    print("  Pharmacist: grace@brightcare.pharmacy / pharmacy123")
    print("  Cashier:    lena@brightcare.pharmacy / pharmacy123")


if __name__ == "__main__":
    from app.core.db import SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        run(session)
    finally:
        session.close()
