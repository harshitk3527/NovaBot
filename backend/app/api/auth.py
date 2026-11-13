from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError

from app.core.config import get_settings
from app.core.deps import get_current_user, require_role
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import AuditLog, RefreshToken, User, UserRole
from app.services.abuse import allow_request, clear_login_failures, login_locked, record_login_failure
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> tuple[TokenResponse, RefreshToken]:
    settings = get_settings()
    access_token, _ = create_token(
        user.id, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_token, jti = create_token(
        user.id, "refresh", timedelta(days=settings.refresh_token_expire_days)
    )
    record = RefreshToken(
        jti=jti,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token), record


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> User:
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=UserRole.CUSTOMER,
        tenant_id=UUID(get_settings().default_tenant_id),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from None
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    if not await allow_request("login-ip", ip, get_settings().login_rate_limit_per_minute):
        db.add(AuditLog(action="rate_limit.login", ip=ip, details=None))
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many login attempts")
    if await login_locked(payload.email):
        db.add(AuditLog(action="auth.login_locked", ip=ip, details=None))
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many login attempts")
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        await record_login_failure(payload.email)
        db.add(AuditLog(user_id=user.id if user else None, action="auth.login_failed", ip=ip, details=None))
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        await record_login_failure(payload.email)
        db.add(AuditLog(user_id=user.id, action="auth.login_failed", ip=ip, details=None))
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await clear_login_failures(payload.email)
    tokens, refresh_record = _tokens(user)
    db.add(refresh_record)
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, "refresh")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from None

    record = await db.get(RefreshToken, claims["jti"])
    now = datetime.now(timezone.utc)
    if record is None or record.revoked_at is not None or record.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = await db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    record.revoked_at = now
    tokens, replacement = _tokens(user)
    db.add(replacement)
    await db.commit()
    return tokens


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/admin-test", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def admin_test() -> dict[str, str]:
    return {"message": "admin access granted"}