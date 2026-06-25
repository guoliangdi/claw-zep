"""Palantir 企业推演工作台路由。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import ProjectContext, get_db, get_project_context, require_permissions
from core.services.retrieval import retrieval_service
from schemas.palantir import ReasoningRequest, ReasoningResponse

router = APIRouter()


@router.post("/reason", response_model=ReasoningResponse,
             dependencies=[Depends(require_permissions("graph:read"))])
async def reason(
    payload: ReasoningRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    """自然语言业务问题 → 因果链路推演 → 图谱+记忆树溯源。"""
    from core.permissions import resolve_project_scope

    pids = await resolve_project_scope(db, ctx.user, ctx.project, fusion=payload.fusion)
    return await retrieval_service.reason(db, ctx.project, payload, project_ids=pids)
