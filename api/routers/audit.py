"""审计日志路由：多条件筛选查看。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_current_user,
    get_db,
    get_effective_tenant_id,
    require_permissions,
)
from api.routers._common import paginate
from models.audit import AuditLog
from schemas.audit import AuditLogOut
from schemas.auth import CurrentUser
from schemas.common import PaginatedResponse, PaginationParams

router = APIRouter(dependencies=[Depends(require_permissions("audit:read"))])


@router.get("", response_model=PaginatedResponse[AuditLogOut])
async def list_audit_logs(
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    result: str | None = Query(default=None),
    created_at_gte: datetime | None = Query(default=None),
    created_at_lte: datetime | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    current: CurrentUser = Depends(get_current_user),
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if project_id:
        stmt = stmt.where(AuditLog.project_id == project_id)
    if result:
        stmt = stmt.where(AuditLog.result == result)
    if created_at_gte:
        stmt = stmt.where(AuditLog.created_at >= created_at_gte)
    if created_at_lte:
        stmt = stmt.where(AuditLog.created_at <= created_at_lte)
    stmt = stmt.order_by(AuditLog.created_at.desc())
    return await paginate(db, stmt, pagination, AuditLogOut)
