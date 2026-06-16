"""认证路由：登录、刷新、当前用户、改密。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from core.config import settings
from core.exceptions import UnauthorizedError
from core.permissions import resolve_permissions
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from core.services.audit_service import write_audit
from models.audit import AuditAction
from models.user import User, UserStatus
from schemas.auth import (
    ChangePasswordRequest,
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        if user is not None:
            user.failed_login_count += 1
        await write_audit(
            db, action=AuditAction.LOGIN_FAILED.value, user_email=payload.email,
            result="failure", ip_address=request.client.host if request.client else None,
        )
        raise UnauthorizedError("邮箱或密码错误")
    if user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedError("账号已被禁用或锁定")

    user.last_login_at = datetime.now(timezone.utc)
    user.failed_login_count = 0

    access = create_access_token(user.id, user.email, user.system_role, user.tenant_id)
    refresh = create_refresh_token(user.id)
    await write_audit(
        db, action=AuditAction.LOGIN.value, tenant_id=user.tenant_id,
        user_id=user.id, user_email=user.email,
        ip_address=request.client.host if request.client else None,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    data = decode_token(payload.refresh_token)
    if data.get("type") != "refresh":
        raise UnauthorizedError("需要 refresh token")
    user = await db.get(User, data.get("sub"))
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedError("用户不可用")
    access = create_access_token(user.id, user.email, user.system_role, user.tenant_id)
    refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=CurrentUser)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, current_user.id)
    if user is None or not verify_password(payload.old_password, user.hashed_password):
        raise UnauthorizedError("原密码错误")
    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    await write_audit(
        db, action=AuditAction.USER_UPDATE.value, user_id=user.id,
        user_email=user.email, resource_type="user", resource_id=user.id,
        extra={"change": "password"},
    )
    return {"success": True, "message": "密码已更新"}
