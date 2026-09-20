import logging
from contextlib import asynccontextmanager
from time import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.responses import AppError, app_error_handler, error_payload, unhandled_error_handler
from app.ai.router import router as copilot_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.inventory.router import router as products_router
from app.modules.inventory.router import stock_router
from app.modules.purchases.router import receiving_router
from app.modules.purchases.router import router as purchases_router
from app.modules.reports.router import router as reports_router
from app.modules.sales.router import customers_router
from app.modules.sales.router import returns_router
from app.modules.sales.router import router as sales_router
from app.modules.settings.router import notifications_router
from app.modules.settings.router import router as settings_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.users.router import router as users_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("aetherqore")

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment != "test":
        from app.core.dates import repair_short_year_expiries
        from app.core.db import SessionLocal

        db = SessionLocal()
        try:
            n = repair_short_year_expiries(db)
            if n:
                logger.info("repaired %s expiry dates with two-digit years", n)
        except Exception:
            logger.exception("could not repair short-year expiry dates")
        finally:
            db.close()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/docs", redoc_url="/redoc", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=error_payload("VALIDATION_ERROR", "Invalid request", {"errors": exc.errors()}))


@app.exception_handler(IntegrityError)
async def integrity_handler(_: Request, exc: IntegrityError):
    logger.warning("integrity error: %s", exc)
    return JSONResponse(status_code=409, content=error_payload("CONFLICT", "The request conflicts with existing data"))


_login_hits: dict[str, list[float]] = {}


@app.middleware("http")
async def login_rate_limit(request: Request, call_next):
    if settings.environment != "test" and request.url.path == "/auth/login" and request.method == "POST":
        ip = request.client.host if request.client else "unknown"
        now = time()
        hits = [t for t in _login_hits.get(ip, []) if now - t < 60]
        if len(hits) >= 8:
            return JSONResponse(status_code=429, content=error_payload("RATE_LIMITED", "Too many login attempts. Try again shortly."))
        hits.append(now)
        _login_hits[ip] = hits
    return await call_next(request)


@app.get("/health")
def health():
    from app.core.db import database_ready

    db_ok = database_ready()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": settings.app_name,
        "environment": settings.environment,
        "database": "ok" if db_ok else "error",
        "ai": {
            "enabled": settings.ai_enabled,
            "mode": "llm" if settings.ai_enabled else "local-data",
        },
        "data_dir": str(settings.resolved_data_dir) if settings.environment != "test" else None,
    }


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(products_router)
app.include_router(stock_router)
app.include_router(suppliers_router)
app.include_router(purchases_router)
app.include_router(receiving_router)
app.include_router(sales_router)
app.include_router(returns_router)
app.include_router(customers_router)
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(copilot_router)
app.include_router(audit_router)
app.include_router(notifications_router)
