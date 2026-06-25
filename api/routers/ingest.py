"""
结构化直灌路由
==============
POST /api/v1/ingest/bulk —— 上游（worldmonitor 等）以项目 API Key 推送已抽好的
实体/关系三元组，单事务落地三库，跳过 LLM。
也支持 JWT + X-Project-ID 调用（需 memory:write 权限）。
"""
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    APIKeyPrincipal,
    ProjectContext,
    get_db,
    get_project_api_principal,
    get_project_context,
    require_permissions,
)
from core.services.audit_service import write_audit
from core.services.bulk_ingest import ingest_bulk
from models.audit import AuditAction
from schemas.ingest import BulkIngestRequest, BulkIngestResponse

router = APIRouter()


@router.post("/bulk", response_model=BulkIngestResponse)
async def bulk_ingest_via_apikey(
    payload: BulkIngestRequest,
    principal: APIKeyPrincipal = Depends(get_project_api_principal),
    db: AsyncSession = Depends(get_db),
):
    """API Key 鉴权（worldmonitor 推送主路径）。"""
    resp = await ingest_bulk(db, principal.project, payload)
    await write_audit(
        db, action=AuditAction.EPISODE_INGEST.value, tenant_id=principal.tenant_id,
        project_id=principal.project_id, resource_type="bulk_ingest",
        extra={"source": payload.source, "records": resp.records,
               "entities": resp.entities, "relations": resp.relations},
    )
    return resp


@router.post("/bulk/jwt", response_model=BulkIngestResponse,
             dependencies=[Depends(require_permissions("memory:write"))])
async def bulk_ingest_via_jwt(
    payload: BulkIngestRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    """JWT + X-Project-ID 鉴权（后台/调试调用）。"""
    resp = await ingest_bulk(db, ctx.project, payload)
    await write_audit(
        db, action=AuditAction.EPISODE_INGEST.value, resource_type="bulk_ingest",
        extra={"source": payload.source, "records": resp.records},
    )
    return resp
