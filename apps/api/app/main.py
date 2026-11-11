import ipaddress

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


def _is_trusted_proxy(host: str) -> bool:
    """Return True only when the direct TCP peer is loopback or RFC-1918/ULA.
    Caddy runs on the same host or on the same Docker network; public peers are
    never trusted reverse proxies in this deployment."""
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return False


class _RealIPMiddleware(BaseHTTPMiddleware):
    """Populate request.client with the real IP from X-Forwarded-For only when
    the direct TCP peer is a trusted reverse proxy (loopback or RFC-1918/ULA).
    Accepts the leftmost address in the header; the full chain is not trusted.
    Without this guard an attacker could spoof any IP to bypass rate limiting."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        peer = request.client.host if request.client else ""
        if peer and _is_trusted_proxy(peer):
            forwarded_for = request.headers.get("X-Forwarded-For", "")
            real_ip = forwarded_for.split(",")[0].strip()
            if real_ip:
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
