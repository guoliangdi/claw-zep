"""
OpenClaw 远程记忆接入路由（服务端）
=====================================
以『项目级 API Key』鉴权（X-API-Key: cz_live_...），供 OpenClaw 客户端 /
龙虾移动端 Agent 进行云端记忆托管与多设备同步，替换其本地文件存储。

端点：
  POST /memory/add        写入记忆（异步抽取入图谱/向量/记忆树）
  POST /memory/search     混合检索
  GET  /sync              拉取自 since 以来的记忆变更（多设备增量同步）
  PUT  /documents/{key}   存储/更新命名记忆文档（Markdown）
  GET  /documents/{key}   读取命名记忆文档
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import APIKeyPrincipal, get_db, get_project_api_principal
from core.memory_tree.service import memory_tree_service, node_to_dict
from core.services.graphiti_orchestrator import graphiti_orchestrator
from core.services.retrieval import retrieval_service
from models.graph import Episode, EpisodeStatus
from models.memory_tree import MemoryTreeNode, TreeLayer
from schemas.memory import (
    MemoryAddRequest,
    MemoryAddResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/whoami")
async def whoami(principal: APIKeyPrincipal = Depends(get_project_api_principal)) -> dict:
    return {
        "project_id": principal.project_id,
        "tenant_id": principal.tenant_id,
        "project_name": principal.project.name,
    }


@router.post("/memory/add", response_model=MemoryAddResponse)
async def add_memory(
    payload: MemoryAddRequest,
    principal: APIKeyPrincipal = Depends(get_project_api_principal),
    db: AsyncSession = Depends(get_db),
):
    content = payload.content or "\n".join(
        f"{m.role}: {m.content}" for m in (payload.messages or [])
    )
    episode = Episode(
        tenant_id=principal.tenant_id, project_id=principal.project_id,
        name=payload.name, content=content, episode_type=payload.episode_type,
        source=payload.source or "openclaw", group_id=payload.group_id,
        valid_from=payload.valid_from or utcnow(), status=EpisodeStatus.PENDING.value,
    )
    db.add(episode)
    await db.flush()

    if payload.sync:
        result = await graphiti_orchestrator.ingest_episode(db, episode.id)
        return MemoryAddResponse(
            episode_id=episode.id, status=result["status"],
            extracted_entities=result["entities"], extracted_relations=result["relations"],
        )
    try:
        from core.tasks.graphiti_tasks import process_episode

        ar = process_episode.delay(episode.id)
        episode.celery_task_id = ar.id
        return MemoryAddResponse(episode_id=episode.id, status="pending", task_id=ar.id)
    except Exception:
        result = await graphiti_orchestrator.ingest_episode(db, episode.id)
        return MemoryAddResponse(
            episode_id=episode.id, status=result["status"],
            extracted_entities=result["entities"], extracted_relations=result["relations"],
        )


@router.post("/memory/search", response_model=SearchResponse)
async def search_memory(
    payload: SearchRequest,
    principal: APIKeyPrincipal = Depends(get_project_api_principal),
    db: AsyncSession = Depends(get_db),
):
    return await retrieval_service.search(db, principal.project, payload)


@router.get("/sync")
async def sync(
    since: Optional[datetime] = Query(default=None, description="拉取此时间之后的变更"),
    limit: int = Query(default=200, le=1000),
    principal: APIKeyPrincipal = Depends(get_project_api_principal),
    db: AsyncSession = Depends(get_db),
):
    """多设备增量同步：返回 since 之后新增/更新的 Episode 与记忆树文档节点。"""
    ep_stmt = select(Episode).where(Episode.project_id == principal.project_id)
    node_stmt = select(MemoryTreeNode).where(
        MemoryTreeNode.project_id == principal.project_id
    )
    if since:
        ep_stmt = ep_stmt.where(Episode.updated_at > since)
        node_stmt = node_stmt.where(MemoryTreeNode.updated_at > since)
    ep_stmt = ep_stmt.order_by(Episode.updated_at.desc()).limit(limit)
    node_stmt = node_stmt.order_by(MemoryTreeNode.updated_at.desc()).limit(limit)

    episodes = (await db.scalars(ep_stmt)).all()
    nodes = (await db.scalars(node_stmt)).all()
    return {
        "server_time": utcnow().isoformat(),
        "episodes": [
            {"id": e.id, "content": e.content, "group_id": e.group_id,
             "status": e.status, "updated_at": e.updated_at.isoformat()}
            for e in episodes
        ],
        "documents": [node_to_dict(n) for n in nodes],
    }


@router.put("/documents/{doc_key}")
async def put_document(
    doc_key: str,
    payload: dict,
    principal: APIKeyPrincipal = Depends(get_project_api_principal),
    db: AsyncSession = Depends(get_db),
):
    """
    存储/更新命名记忆文档（按 doc_key 唯一），映射为 SOURCE 层记忆树节点。
    payload: {"title": str, "content_markdown": str}
    多设备以同一 doc_key 写入即实现统一云端存储 + 覆盖同步。
    """
    title = payload.get("title") or doc_key
    content = payload.get("content_markdown") or ""

    existing = await db.scalar(
        select(MemoryTreeNode).where(
            MemoryTreeNode.project_id == principal.project_id,
            MemoryTreeNode.topic_id == f"openclaw:{doc_key}",
        )
    )
    if existing:
        node = await memory_tree_service.update_node(
            db, principal.project_id, existing.id,
            title=title, content_markdown=content,
            change_summary="openclaw sync update",
        )
    else:
        node = await memory_tree_service.create_node(
            db, principal.tenant_id, principal.project_id,
            tree_layer=TreeLayer.SOURCE.value, title=title,
            content_markdown=content, topic_id=f"openclaw:{doc_key}",
        )
    return {"success": True, "doc_key": doc_key, "node_id": node.id, "version": node.version}


@router.get("/documents/{doc_key}")
async def get_document(
    doc_key: str,
    principal: APIKeyPrincipal = Depends(get_project_api_principal),
    db: AsyncSession = Depends(get_db),
):
    node = await db.scalar(
        select(MemoryTreeNode).where(
            MemoryTreeNode.project_id == principal.project_id,
            MemoryTreeNode.topic_id == f"openclaw:{doc_key}",
        )
    )
    if node is None:
        return {"doc_key": doc_key, "exists": False, "content_markdown": None}
    return {
        "doc_key": doc_key, "exists": True, "node_id": node.id,
        "title": node.title, "content_markdown": node.content_markdown,
        "version": node.version, "updated_at": node.updated_at.isoformat(),
    }
