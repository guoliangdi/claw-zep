"""Playground 调试台路由：在线入库 + 在线检索（自定义时序与权重）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import ProjectContext, get_db, get_project_context, require_permissions
from core.services.graphiti_orchestrator import graphiti_orchestrator
from core.services.retrieval import retrieval_service
from models.graph import Episode, EpisodeStatus
from schemas.memory import (
    MemoryAddRequest,
    MemoryAddResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter()


@router.post("/ingest", response_model=MemoryAddResponse,
             dependencies=[Depends(require_permissions("memory:write"))])
async def playground_ingest(
    payload: MemoryAddRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    """调试入库：始终同步抽取并即时返回结果。"""
    content = payload.content or "\n".join(
        f"{m.role}: {m.content}" for m in (payload.messages or [])
    )
    episode = Episode(
        tenant_id=ctx.tenant_id, project_id=ctx.project_id, name=payload.name,
        content=content, episode_type=payload.episode_type, source=payload.source,
        group_id=payload.group_id,
        valid_from=payload.valid_from or datetime.now(timezone.utc),
        status=EpisodeStatus.PENDING.value,
    )
    db.add(episode)
    await db.flush()
    result = await graphiti_orchestrator.ingest_episode(db, episode.id)
    return MemoryAddResponse(
        episode_id=episode.id, status=result["status"],
        extracted_entities=result["entities"], extracted_relations=result["relations"],
    )


@router.post("/search", response_model=SearchResponse,
             dependencies=[Depends(require_permissions("memory:read"))])
async def playground_search(
    payload: SearchRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    """调试检索：支持自定义时序范围与混合权重。"""
    return await retrieval_service.search(db, ctx.project, payload)
