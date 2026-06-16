"""时序快照工作台路由：快照、差异对比、实体生命周期。"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import ProjectContext, get_db, get_project_context, require_permissions
from core.adapters.graph_repo import pg_graph_repo
from core.temporal.engine import TemporalEngine
from models.graph import GraphEntityMeta, GraphRelationMeta
from models.memory_tree import MemoryTreeNode
from schemas.temporal import (
    DiffItem,
    EntityLifecycleRequest,
    EntityLifecycleResponse,
    LifecycleEvent,
    SnapshotDiffRequest,
    SnapshotDiffResponse,
    SnapshotRequest,
    SnapshotResponse,
    SnapshotStats,
)

router = APIRouter(dependencies=[Depends(require_permissions("temporal:read"))])


def _entity_dict(e: GraphEntityMeta) -> dict:
    return {"kuzu_uuid": e.kuzu_uuid, "name": e.name, "entity_type": e.entity_type,
            "summary": e.summary, "version": e.version,
            "valid_from": e.valid_from, "valid_until": e.valid_until}


def _relation_dict(r: GraphRelationMeta) -> dict:
    return {"kuzu_uuid": r.kuzu_uuid, "relation_type": r.relation_type, "fact": r.fact,
            "source": r.source_entity_name, "target": r.target_entity_name,
            "version": r.version, "valid_from": r.valid_from, "valid_until": r.valid_until}


@router.post("/snapshot", response_model=SnapshotResponse)
async def generate_snapshot(
    payload: SnapshotRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    entities, relations, tree = [], [], []
    if payload.include_entities:
        rows = await TemporalEngine.snapshot(db, GraphEntityMeta, ctx.project_id, payload.as_of)
        entities = [_entity_dict(e) for e in rows]
    if payload.include_relations:
        rows = await TemporalEngine.snapshot(db, GraphRelationMeta, ctx.project_id, payload.as_of)
        relations = [_relation_dict(r) for r in rows]
    if payload.include_memory_tree:
        rows = await TemporalEngine.snapshot(db, MemoryTreeNode, ctx.project_id, payload.as_of)
        tree = [{"id": n.id, "title": n.title, "tree_layer": n.tree_layer,
                 "version": n.version} for n in rows]
    return SnapshotResponse(
        project_id=ctx.project_id, as_of=payload.as_of,
        stats=SnapshotStats(entity_count=len(entities), relation_count=len(relations),
                            memory_tree_node_count=len(tree)),
        entities=entities, relations=relations, memory_tree_nodes=tree,
    )


@router.post("/diff", response_model=SnapshotDiffResponse)
async def snapshot_diff(
    payload: SnapshotDiffRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    changes: list[DiffItem] = []
    added = removed = modified = 0

    async def diff_model(model, kind, to_dict, key="kuzu_uuid"):
        nonlocal added, removed, modified
        before = {getattr(r, key): r for r in
                  await TemporalEngine.snapshot(db, model, ctx.project_id, payload.from_time)}
        after = {getattr(r, key): r for r in
                 await TemporalEngine.snapshot(db, model, ctx.project_id, payload.to_time)}
        for k, r in after.items():
            if k not in before:
                added += 1
                changes.append(DiffItem(change_type="added", kind=kind, id=k,
                                        name=getattr(r, "name", None), after=to_dict(r)))
            elif before[k].version != r.version:
                modified += 1
                changes.append(DiffItem(change_type="modified", kind=kind, id=k,
                                        name=getattr(r, "name", None),
                                        before=to_dict(before[k]), after=to_dict(r)))
        for k, r in before.items():
            if k not in after:
                removed += 1
                changes.append(DiffItem(change_type="removed", kind=kind, id=k,
                                        name=getattr(r, "name", None), before=to_dict(r)))

    if payload.include_entities:
        await diff_model(GraphEntityMeta, "entity", _entity_dict)
    if payload.include_relations:
        await diff_model(GraphRelationMeta, "relation", _relation_dict)

    return SnapshotDiffResponse(
        project_id=ctx.project_id, from_time=payload.from_time, to_time=payload.to_time,
        added=added, removed=removed, modified=modified, changes=changes,
    )


@router.post("/lifecycle", response_model=EntityLifecycleResponse)
async def entity_lifecycle(
    payload: EntityLifecycleRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    kuzu_uuid = payload.entity_kuzu_uuid
    name = payload.entity_name
    if not kuzu_uuid and name:
        found = await pg_graph_repo.find_entities_by_name(db, ctx.project_id, name, limit=1)
        if found:
            kuzu_uuid = found[0].kuzu_uuid
    if not kuzu_uuid:
        return EntityLifecycleResponse(entity_name=name, total_versions=0, events=[])

    history = await TemporalEngine.get_history(
        db, GraphEntityMeta, "kuzu_uuid", kuzu_uuid, ctx.project_id
    )
    events = []
    for i, h in enumerate(history):
        change = "created" if i == 0 else ("expired" if h.valid_until else "updated")
        events.append(LifecycleEvent(
            version=h.version, valid_from=h.valid_from, valid_until=h.valid_until,
            source=h.source, summary=h.summary, change=change, snapshot=_entity_dict(h),
        ))
    return EntityLifecycleResponse(
        entity_name=history[-1].name if history else name,
        entity_kuzu_uuid=kuzu_uuid, total_versions=len(history), events=events,
    )
