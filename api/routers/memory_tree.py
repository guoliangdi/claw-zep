"""记忆树路由：节点 CRUD、树形读取、版本回溯、导出。"""
import io
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import ProjectContext, get_db, get_project_context, require_permissions
from core.memory_tree.builder import memory_tree_builder
from core.memory_tree.exporter import memory_tree_exporter
from core.memory_tree.service import memory_tree_service, node_to_dict
from core.services.audit_service import write_audit
from models.audit import AuditAction
from schemas.memory_tree import (
    MemoryTreeExportRequest,
    MemoryTreeExportResponse,
    MemoryTreeNodeCreate,
    MemoryTreeNodeOut,
    MemoryTreeNodeTree,
    MemoryTreeNodeUpdate,
    MemoryTreeNodeVersionOut,
)

router = APIRouter(dependencies=[Depends(require_permissions("memory_tree:read"))])


@router.get("/tree", response_model=list[MemoryTreeNodeTree])
async def get_tree(
    tree_layer: str = Query(default="source", description="source|topic|global"),
    as_of: datetime | None = Query(default=None),
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    return await memory_tree_service.get_tree(db, ctx.project_id, tree_layer, as_of=as_of)


@router.get("/nodes", response_model=list[MemoryTreeNodeOut])
async def list_nodes(
    tree_layer: str | None = Query(default=None),
    parent_id: str | None = Query(default=None),
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    nodes = await memory_tree_service.list_nodes(
        db, ctx.project_id, tree_layer=tree_layer, parent_id=parent_id
    )
    return [node_to_dict(n) for n in nodes]


@router.get("/nodes/{node_id}", response_model=MemoryTreeNodeOut)
async def get_node(
    node_id: str,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    node = await memory_tree_service.get_node(db, ctx.project_id, node_id)
    return node_to_dict(node)


@router.post("/nodes", response_model=MemoryTreeNodeOut, status_code=201,
             dependencies=[Depends(require_permissions("memory_tree:write"))])
async def create_node(
    payload: MemoryTreeNodeCreate,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    node = await memory_tree_service.create_node(
        db, ctx.tenant_id, ctx.project_id,
        tree_layer=payload.tree_layer, title=payload.title,
        content_markdown=payload.content_markdown, parent_id=payload.parent_id,
        topic_id=payload.topic_id, topic_label=payload.topic_label,
        entity_refs=payload.entity_refs, source_episode_id=payload.source_episode_id,
        order_index=payload.order_index, valid_from=payload.valid_from,
    )
    await write_audit(
        db, action=AuditAction.MEMORY_TREE_CREATE.value, resource_type="memory_tree_node",
        resource_id=node.id,
    )
    await db.flush()
    return node_to_dict(node)


@router.patch("/nodes/{node_id}", response_model=MemoryTreeNodeOut,
              dependencies=[Depends(require_permissions("memory_tree:write"))])
async def update_node(
    node_id: str, payload: MemoryTreeNodeUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    node = await memory_tree_service.update_node(
        db, ctx.project_id, node_id, changed_by=ctx.user.id,
        **payload.model_dump(exclude_unset=True),
    )
    await write_audit(
        db, action=AuditAction.MEMORY_TREE_UPDATE.value, resource_type="memory_tree_node",
        resource_id=node.id,
    )
    await db.flush()
    return node_to_dict(node)


@router.delete("/nodes/{node_id}",
               dependencies=[Depends(require_permissions("memory_tree:delete"))])
async def delete_node(
    node_id: str, cascade: bool = Query(default=True),
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    count = await memory_tree_service.delete_node(db, ctx.project_id, node_id, cascade=cascade)
    await write_audit(
        db, action=AuditAction.MEMORY_TREE_DELETE.value, resource_type="memory_tree_node",
        resource_id=node_id, extra={"deleted": count},
    )
    await db.flush()
    return {"success": True, "deleted": count}


@router.get("/nodes/{node_id}/versions", response_model=list[MemoryTreeNodeVersionOut])
async def list_versions(
    node_id: str,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    versions = await memory_tree_service.list_versions(db, ctx.project_id, node_id)
    return [MemoryTreeNodeVersionOut.model_validate(v) for v in versions]


@router.post("/nodes/{node_id}/rollback/{version_number}", response_model=MemoryTreeNodeOut,
             dependencies=[Depends(require_permissions("memory_tree:write"))])
async def rollback_node(
    node_id: str, version_number: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    node = await memory_tree_service.rollback(
        db, ctx.project_id, node_id, version_number, changed_by=ctx.user.id
    )
    await db.flush()
    return node_to_dict(node)


@router.post("/rebuild", dependencies=[Depends(require_permissions("memory_tree:write"))])
async def rebuild_trees(
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    """手动触发主题树聚合 + 全局摘要。"""
    topics = await memory_tree_builder.build_topic_tree(db, ctx.tenant_id, ctx.project_id)
    g = await memory_tree_builder.build_global_summary(db, ctx.tenant_id, ctx.project_id)
    await db.flush()
    return {"success": True, "topics": len(topics), "global": bool(g)}


@router.post("/export")
async def export_tree(
    payload: MemoryTreeExportRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    files = await memory_tree_exporter.export(
        db, ctx.project_id, tree_layer=payload.tree_layer, fmt=payload.format
    )
    await write_audit(
        db, action=AuditAction.MEMORY_TREE_EXPORT.value, resource_type="memory_tree",
        extra={"format": payload.format, "files": len(files)},
    )
    await db.flush()

    # 打包为 zip 流式返回
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="memory_tree_{ctx.project_id[:8]}.zip"'},
    )
