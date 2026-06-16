"""记忆读写路由：写入(add) + 混合检索(search)，对标 Zep memory API。"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import ProjectContext, get_db, get_project_context, require_permissions
from core.services.audit_service import write_audit
from core.services.graphiti_orchestrator import graphiti_orchestrator
from core.services.retrieval import retrieval_service
from models.audit import AuditAction
from models.graph import Episode, EpisodeStatus
from schemas.memory import (
    MemoryAddRequest,
    MemoryAddResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compose_content(payload: MemoryAddRequest) -> str:
    if payload.messages:
        return "\n".join(
            f"{m.role}: {m.content}" for m in payload.messages
        )
    return payload.content or ""


@router.post("/add", response_model=MemoryAddResponse,
             dependencies=[Depends(require_permissions("memory:write"))])
async def add_memory(
    payload: MemoryAddRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    content = _compose_content(payload)
    episode = Episode(
        tenant_id=ctx.tenant_id,
        project_id=ctx.project_id,
        name=payload.name,
        content=content,
        episode_type=payload.episode_type,
        source=payload.source,
        group_id=payload.group_id,
        valid_from=payload.valid_from or utcnow(),
        status=EpisodeStatus.PENDING.value,
    )
    db.add(episode)
    await db.flush()

    await write_audit(
        db, action=AuditAction.EPISODE_INGEST.value, tenant_id=ctx.tenant_id,
        project_id=ctx.project_id, resource_type="episode", resource_id=episode.id,
    )

    if payload.sync:
        # 同步抽取（小批量/调试）
        result = await graphiti_orchestrator.ingest_episode(db, episode.id)
        return MemoryAddResponse(
            episode_id=episode.id, status=result["status"],
            extracted_entities=result["entities"], extracted_relations=result["relations"],
        )

    # 异步入队
    task_id = None
    try:
        from core.tasks.graphiti_tasks import process_episode

        async_result = process_episode.delay(episode.id)
        task_id = async_result.id
        episode.celery_task_id = task_id
    except Exception:
        # Broker 不可用时回退同步处理，保证可用
        result = await graphiti_orchestrator.ingest_episode(db, episode.id)
        return MemoryAddResponse(
            episode_id=episode.id, status=result["status"],
            extracted_entities=result["entities"], extracted_relations=result["relations"],
        )
    return MemoryAddResponse(episode_id=episode.id, status="pending", task_id=task_id)


@router.post("/search", response_model=SearchResponse,
             dependencies=[Depends(require_permissions("memory:read"))])
async def search_memory(
    payload: SearchRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    return await retrieval_service.search(db, ctx.project, payload)
