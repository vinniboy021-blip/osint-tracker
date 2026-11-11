from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_client import make_asgi_app
from redis import Redis
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth import router as auth_router
from app.config import settings
from app.db import SessionLocal
from app.observability import RequestLoggingMiddleware, configure_logging
from app.routes.collection import router as collection_router
from app.routes.core import router as core_router
from app.routes.intelligence import router as intelligence_router
from app.routes.kali import router as kali_router


class _RealIPMiddleware(BaseHTTPMiddleware):
    """Populate request.client with the real IP from X-Forwarded-For when the
    immediate peer is a trusted reverse proxy (Caddy, in this deployment).
    Only the first address in the header is used; the full chain is not trusted."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")
        real_ip = forwarded_for[0].strip() if forwarded_for else ""
        if real_ip:
            # Replace the connection-level address so rate limiting and audit
            # logging record the client IP, not the proxy's loopback address.
            from starlette.datastructures import Address
            request.scope["client"] = (real_ip, 0)
        return await call_next(request)


configure_logging()
app = FastAPI(
    title="OSINT Tracker API",
    version="0.1.0",
    description="Coleta OSINT autorizada com proveniência auditável",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(_RealIPMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(core_router, prefix="/api/v1")
app.include_router(kali_router, prefix="/api/v1")
app.include_router(collection_router, prefix="/api/v1")
app.include_router(intelligence_router, prefix="/api/v1")
if settings.metrics_enabled:
    app.mount("/metrics/prometheus", make_asgi_app())


@app.get("/", include_in_schema=False)
def root():
    return {"name": "OSINT Tracker", "docs": "/docs", "status": "ok"}


@app.get("/live", include_in_schema=False)
def live():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
def ready():
    """Return readiness only when the database and Redis are reachable."""
    checks: dict[str, str] = {}
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        try:
            redis_client.ping()
        finally:
            redis_client.close()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
    if any(value != "ok" for value in checks.values()):
        return JSONResponse({"status": "not_ready", "checks": checks}, status_code=503)
    return {"status": "ready", "checks": checks}
