"""Server-side opaque sessions, CSRF protection, RBAC and bounded login attempts."""

import hashlib
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AuditLog, AuthSession, Investigation, InvestigationMember, User, utcnow

router = APIRouter(prefix="/auth", tags=["Autenticação"])
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
_local_attempts: dict[str, tuple[int, float]] = {}
_local_lock = threading.Lock()
_redis_client = redis.Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def user_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def audit(
    db: Session,
    user: User | None,
    action: str,
    object_type: str,
    object_id: str | None = None,
    investigation_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            investigation_id=investigation_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details or {},
        )
    )


def _counter(key: str, window: int, increment: bool = False) -> int:
    try:
        if increment:
            # INCR+EXPIRE atomically: no immortal throttle key if a process dies.
            script = "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n"
            return int(_redis_client.eval(script, 1, key, window))
        value = _redis_client.get(key)
        return int(value or 0)
    except redis.RedisError:
        if settings.environment == "production":
            raise HTTPException(503, "Proteção de autenticação indisponível") from None
        with _local_lock:
            now = time.monotonic()
            for expired in [item for item, (_, expires) in _local_attempts.items() if expires < now]:
                _local_attempts.pop(expired, None)
            count, expires = _local_attempts.get(key, (0, now + window))
            count += int(increment)
            _local_attempts[key] = (count, expires)
            return count


def request_rate_limit(request: Request) -> None:
    identity = request.client.host if request.client else "unknown"
    key = "osint:rate:" + hashlib.sha256(identity.encode()).hexdigest()
    if _counter(key, 60, increment=True) > settings.rate_limit_per_minute:
        raise HTTPException(429, "Limite de requisições atingido", headers={"Retry-After": "60"})


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get(settings.session_cookie)
    if not raw:
        raise HTTPException(401, "Autenticação necessária")
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if not session or utc(session.expires_at) <= utcnow():
        raise HTTPException(401, "Sessão expirada ou inválida")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Usuário inativo")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(session.csrf_token, csrf):
            raise HTTPException(403, "Token CSRF inválido")
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            raise HTTPException(403, "Origem não autorizada")
    request.state.auth_session = session
    request.state.user_id = user.id
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Permissão de administrador necessária")
    return user


def investigation_access(
    db: Session, user: User, investigation_id: str, write: bool = False
) -> Investigation:
    investigation = db.get(Investigation, investigation_id)
    if not investigation:
        raise HTTPException(404, "Investigação não encontrada")
    if user.role == "admin":
        return investigation
    member = db.scalar(
        select(InvestigationMember).where(
            InvestigationMember.investigation_id == investigation_id, InvestigationMember.user_id == user.id
        )
    )
    is_owner = investigation.owner_id == user.id
    if not is_owner and not member:
        raise HTTPException(404, "Investigação não encontrada")
    if write and (user.role == "viewer" or (not is_owner and member and member.role == "viewer")):
        raise HTTPException(403, "Acesso somente para leitura")
    return investigation


def owner_access(db: Session, user: User, investigation_id: str) -> Investigation:
    investigation = investigation_access(db, user, investigation_id, write=True)
    if user.role != "admin" and investigation.owner_id != user.id:
        raise HTTPException(403, "Apenas responsável pode gerenciar colaboradores")
    return investigation


def _fernet() -> Fernet:
    if not settings.connector_secret_key:
        raise HTTPException(503, "Configure CONNECTOR_SECRET_KEY para armazenar credenciais")
    try:
        return Fernet(settings.connector_secret_key.encode())
    except ValueError:
        raise HTTPException(503, "Chave de configuração inválida") from None


def is_secret_field(key: str) -> bool:
    return any(
        part in key.lower()
        for part in ("token", "secret", "password", "api_key", "auth_key", "authorization")
    )


def encrypt_connector_settings(values: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            result[key] = encrypt_connector_settings(value)
        elif is_secret_field(key) and value is not None:
            result[key] = "encrypted:" + _fernet().encrypt(str(value).encode()).decode()
        else:
            result[key] = value
    return result


def decrypt_connector_settings(values: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            result[key] = decrypt_connector_settings(value)
        elif isinstance(value, str) and value.startswith("encrypted:"):
            try:
                result[key] = _fernet().decrypt(value[10:].encode()).decode()
            except InvalidToken:
                raise ValueError("Não foi possível descriptografar configuração do conector") from None
        else:
            result[key] = value
    return result


def redact_connector_settings(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (
            redact_connector_settings(value)
            if isinstance(value, dict)
            else "••••••••"
            if is_secret_field(key)
            else value
        )
        for key, value in values.items()
    }


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
def login(
    body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> dict[str, Any]:
    origin = request.headers.get("origin")
    if origin and origin not in settings.allowed_origins:
        raise HTTPException(403, "Origem não autorizada")
    email = str(body.email).lower()
    ip = request.client.host if request.client else "unknown"
    key = "osint:login:" + hashlib.sha256(f"{ip}:{email}".encode()).hexdigest()
    ip_key = "osint:login-ip:" + hashlib.sha256(ip.encode()).hexdigest()
    if (
        _counter(key, settings.login_window_seconds) >= settings.login_max_attempts
        or _counter(ip_key, settings.login_window_seconds) >= settings.login_max_attempts * 10
    ):
        raise HTTPException(
            429,
            "Muitas tentativas. Tente novamente depois.",
            headers={"Retry-After": str(settings.login_window_seconds)},
        )
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(body.password, user.password_hash if user else _dummy_hash)
    if not user or not valid or not user.is_active:
        _counter(key, settings.login_window_seconds, True)
        _counter(ip_key, settings.login_window_seconds, True)
        audit(
            db,
            None,
            "auth.login_failed",
            "user",
            details={"email_hash": hashlib.sha256(email.encode()).hexdigest()},
        )
        db.commit()
        raise HTTPException(401, "Credenciais inválidas")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    # Expired session data is bounded without requiring an external maintenance job.
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            csrf_token=csrf_token,
            expires_at=utcnow() + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    audit(db, user, "auth.login", "user", user.id)
    db.commit()
    response.set_cookie(
        settings.session_cookie,
        raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": user_dict(user), "csrf_token": csrf_token}


@router.get("/me")
def me(request: Request, response: Response, user: User = Depends(current_user)) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {"user": user_dict(user), "csrf_token": request.state.auth_session.csrf_token}


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    db.delete(request.state.auth_session)
    audit(db, user, "auth.logout", "user", user.id)
    db.commit()
    response.delete_cookie(
        settings.session_cookie, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )


@router.post("/logout-all")
def logout_all(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Revoga todas as sessões ativas do usuário."""
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(db, user, "auth.logout_all", "user", user.id)
    db.commit()
    response.delete_cookie(
        settings.session_cookie, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
    return {"status": "revoked"}
