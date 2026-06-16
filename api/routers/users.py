"""用户管理路由（租户管理员）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_current_user,
    get_db,
    get_effective_tenant_id,
    require_tenant_admin,
)
from api.routers._common import paginate
from core.exceptions import ConflictError, ForbiddenError, NotFoundError
from core.security import hash_password
from core.services.audit_service import write_audit
from models.audit import AuditAction
from models.user import SystemRole, User, UserStatus
from schemas.auth import CurrentUser
from schemas.common import PaginatedResponse, PaginationParams
from schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(dependencies=[Depends(require_tenant_admin)])


@router.get("", response_model=PaginatedResponse[UserOut])
async def list_users(
    status: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(User.status == status)
    stmt = stmt.order_by(User.created_at.desc())
    return await paginate(db, stmt, pagination, UserOut)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserCreate,
    current: CurrentUser = Depends(get_current_user),
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if await db.scalar(select(User).where(User.email == payload.email)):
        raise ConflictError("邮箱已注册")
    # 租户管理员不能创建超级管理员
    if payload.system_role == SystemRole.SUPER_ADMIN.value and not current.is_super_admin:
        raise ForbiddenError("无权创建超级管理员")
    user = User(
        email=payload.email,
        username=payload.username,
        display_name=payload.display_name,
        hashed_password=hash_password(payload.password),
        system_role=payload.system_role,
        status=UserStatus.ACTIVE.value,
        tenant_id=tenant_id,
    )
    db.add(user)
    await write_audit(
        db, action=AuditAction.USER_CREATE.value, tenant_id=tenant_id,
        resource_type="user", resource_id=user.id, after={"email": user.email},
    )
    await db.flush()
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise NotFoundError("用户不存在")
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str, payload: UserUpdate,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise NotFoundError("用户不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    await write_audit(
        db, action=AuditAction.USER_UPDATE.value, tenant_id=tenant_id,
        resource_type="user", resource_id=user.id,
    )
    await db.flush()
    return UserOut.model_validate(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise NotFoundError("用户不存在")
    user.status = UserStatus.INACTIVE.value
    await write_audit(
        db, action=AuditAction.USER_DELETE.value, tenant_id=tenant_id,
        resource_type="user", resource_id=user.id,
    )
    await db.flush()
    return {"success": True}
