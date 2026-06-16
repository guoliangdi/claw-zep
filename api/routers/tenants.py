"""租户管理路由（超级管理员）。"""
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_super_admin
from api.routers._common import paginate
from core.exceptions import ConflictError, NotFoundError
from core.security import hash_password
from core.services.audit_service import write_audit
from models.audit import AuditAction
from models.tenant import Tenant, TenantStatus
from models.user import SystemRole, User, UserStatus
from schemas.auth import CurrentUser
from schemas.common import PaginatedResponse, PaginationParams
from schemas.tenant import TenantCreate, TenantOut, TenantUpdate

router = APIRouter(dependencies=[Depends(require_super_admin)])


@router.get("", response_model=PaginatedResponse[TenantOut])
async def list_tenants(
    status: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Tenant)
    if status:
        stmt = stmt.where(Tenant.status == status)
    stmt = stmt.order_by(Tenant.created_at.desc())
    return await paginate(db, stmt, pagination, TenantOut)


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    payload: TenantCreate,
    current: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    exists = await db.scalar(select(Tenant).where(Tenant.slug == payload.slug))
    if exists:
        raise ConflictError("租户标识已存在", detail=payload.slug)

    tenant = Tenant(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        contact_email=payload.contact_email,
        status=TenantStatus.ACTIVE.value,
        max_projects=payload.max_projects,
        max_users=payload.max_users,
        max_memory_mb=payload.max_memory_mb,
        max_api_calls_per_day=payload.max_api_calls_per_day,
    )
    db.add(tenant)
    await db.flush()

    # 可选：创建租户初始管理员
    if payload.admin_email and payload.admin_password:
        admin = User(
            email=payload.admin_email,
            username=payload.admin_username or payload.admin_email.split("@")[0],
            hashed_password=hash_password(payload.admin_password),
            system_role=SystemRole.TENANT_ADMIN.value,
            status=UserStatus.ACTIVE.value,
            tenant_id=tenant.id,
        )
        db.add(admin)

    await write_audit(
        db, action=AuditAction.TENANT_CREATE.value, tenant_id=tenant.id,
        resource_type="tenant", resource_id=tenant.id, after={"slug": tenant.slug},
    )
    await db.flush()
    return TenantOut.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("租户不存在")
    return TenantOut.model_validate(tenant)


@router.patch("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: str, payload: TenantUpdate, db: AsyncSession = Depends(get_db)
):
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("租户不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    await write_audit(
        db, action=AuditAction.TENANT_UPDATE.value, tenant_id=tenant.id,
        resource_type="tenant", resource_id=tenant.id,
        after=payload.model_dump(exclude_unset=True),
    )
    await db.flush()
    return TenantOut.model_validate(tenant)


@router.post("/{tenant_id}/suspend", response_model=TenantOut)
async def suspend_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("租户不存在")
    tenant.status = TenantStatus.SUSPENDED.value
    await write_audit(
        db, action=AuditAction.TENANT_SUSPEND.value, tenant_id=tenant.id,
        resource_type="tenant", resource_id=tenant.id,
    )
    await db.flush()
    return TenantOut.model_validate(tenant)
