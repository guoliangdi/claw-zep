"""图谱路由：Episodes 筛选、实体、关系、可视化画布。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import ProjectContext, get_db, get_project_context, require_permissions
from api.routers._common import paginate
from core.adapters.graph_repo import pg_graph_repo
from core.exceptions import NotFoundError
from core.services.audit_service import write_audit
from core.temporal.engine import TemporalEngine
from models.audit import AuditAction
from models.graph import Episode, GraphEntityMeta, GraphRelationMeta
from schemas.common import PaginatedResponse, PaginationParams
from schemas.graph import (
    EntityOut,
    EpisodeOut,
    GraphVisualization,
    RelationOut,
)

router = APIRouter(dependencies=[Depends(require_permissions("graph:read"))])


@router.get("/episodes", response_model=PaginatedResponse[EpisodeOut])
async def list_episodes(
    status: str | None = Query(default=None),
    episode_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    valid_from_gte: datetime | None = Query(default=None),
    valid_from_lte: datetime | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Episode).where(Episode.project_id == ctx.project_id)
    if status:
        stmt = stmt.where(Episode.status == status)
    if episode_type:
        stmt = stmt.where(Episode.episode_type == episode_type)
    if source:
        stmt = stmt.where(Episode.source == source)
    if group_id:
        stmt = stmt.where(Episode.group_id == group_id)
    if search:
        stmt = stmt.where(Episode.content.ilike(f"%{search}%"))
    if valid_from_gte:
        stmt = stmt.where(Episode.valid_from >= valid_from_gte)
    if valid_from_lte:
        stmt = stmt.where(Episode.valid_from <= valid_from_lte)
    stmt = stmt.order_by(Episode.created_at.desc())
    return await paginate(db, stmt, pagination, EpisodeOut)


@router.get("/episodes/{episode_id}", response_model=EpisodeOut)
async def get_episode(
    episode_id: str,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    ep = await db.get(Episode, episode_id)
    if ep is None or ep.project_id != ctx.project_id:
        raise NotFoundError("Episode 不存在")
    return EpisodeOut.model_validate(ep)


@router.get("/entities", response_model=PaginatedResponse[EntityOut])
async def list_entities(
    entity_type: str | None = Query(default=None),
    name: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    include_expired: bool = Query(default=False),
    pagination: PaginationParams = Depends(),
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(GraphEntityMeta).where(GraphEntityMeta.project_id == ctx.project_id)
    if entity_type:
        stmt = stmt.where(GraphEntityMeta.entity_type == entity_type)
    if name:
        stmt = stmt.where(GraphEntityMeta.name.ilike(f"%{name}%"))
    stmt = TemporalEngine.apply_temporal_filter(
        stmt, GraphEntityMeta, as_of=as_of, include_expired=include_expired
    )
    stmt = stmt.order_by(GraphEntityMeta.created_at.desc())
    return await paginate(db, stmt, pagination, EntityOut)


@router.get("/relations", response_model=PaginatedResponse[RelationOut])
async def list_relations(
    relation_type: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    include_expired: bool = Query(default=False),
    pagination: PaginationParams = Depends(),
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(GraphRelationMeta).where(GraphRelationMeta.project_id == ctx.project_id)
    if relation_type:
        stmt = stmt.where(GraphRelationMeta.relation_type == relation_type)
    stmt = TemporalEngine.apply_temporal_filter(
        stmt, GraphRelationMeta, as_of=as_of, include_expired=include_expired
    )
    stmt = stmt.order_by(GraphRelationMeta.created_at.desc())
    return await paginate(db, stmt, pagination, RelationOut)


@router.get("/visualization", response_model=GraphVisualization)
async def visualization(
    as_of: datetime | None = Query(default=None),
    limit: int = Query(default=500, le=2000),
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    viz = await pg_graph_repo.visualization(db, ctx.project_id, as_of=as_of, limit=limit)
    return GraphVisualization(**viz)


@router.delete("/entities/{kuzu_uuid}",
               dependencies=[Depends(require_permissions("graph:delete"))])
async def delete_entity(
    kuzu_uuid: str,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    """逻辑删除：失效该实体当前所有有效版本。"""
    n = await TemporalEngine.expire_logical(
        db, GraphEntityMeta, "kuzu_uuid", kuzu_uuid, ctx.project_id
    )
    if n == 0:
        raise NotFoundError("实体不存在或已失效")
    await write_audit(
        db, action=AuditAction.ENTITY_DELETE.value, resource_type="entity",
        resource_id=kuzu_uuid,
    )
    await db.flush()
    return {"success": True, "expired": n}
