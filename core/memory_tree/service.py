"""
记忆树服务
==========
MemoryTreeNode 的 CRUD、树形装配、版本历史、时序绑定、实体关联。

约定：
  · 内容存 content_markdown（≤64KB），超大走对象存储（content_object_key，Phase 7）
  · entity_refs 以 JSON 数组持久化于 entity_refs_json
  · 每次编辑前快照旧版本入 MemoryTreeNodeVersion，并递增 TemporalMixin.version
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Optional

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import MemoryTreeError, NotFoundError
from models.memory_tree import MemoryTreeNode, MemoryTreeNodeVersion, NodeStatus, TreeLayer

logger = structlog.get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dumps_refs(refs: Optional[List[str]]) -> Optional[str]:
    return json.dumps(refs, ensure_ascii=False) if refs else None


def _loads_refs(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def node_to_dict(node: MemoryTreeNode) -> dict[str, Any]:
    """ORM → API 输出 dict（展开 entity_refs）。"""
    return {
        "id": node.id,
        "tenant_id": node.tenant_id,
        "project_id": node.project_id,
        "tree_layer": node.tree_layer,
        "status": node.status,
        "parent_id": node.parent_id,
        "depth": node.depth,
        "path": node.path,
        "order_index": node.order_index,
        "title": node.title,
        "content_markdown": node.content_markdown,
        "summary": node.summary,
        "topic_id": node.topic_id,
        "topic_label": node.topic_label,
        "entity_refs": _loads_refs(node.entity_refs_json),
        "source_episode_id": node.source_episode_id,
        "period_start": node.period_start,
        "period_end": node.period_end,
        "word_count": node.word_count,
        "child_count": node.child_count,
        "valid_from": node.valid_from,
        "valid_until": node.valid_until,
        "version": node.version,
        "created_at": node.created_at,
        "updated_at": node.updated_at,
    }


class MemoryTreeService:
    # ---------------- 创建 ----------------
    @staticmethod
    async def create_node(
        db: AsyncSession,
        tenant_id: str,
        project_id: str,
        *,
        tree_layer: str,
        title: str,
        content_markdown: Optional[str] = None,
        parent_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        topic_label: Optional[str] = None,
        entity_refs: Optional[List[str]] = None,
        source_episode_id: Optional[str] = None,
        order_index: int = 0,
        valid_from: Optional[datetime] = None,
        summary: Optional[str] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> MemoryTreeNode:
        depth = 0
        path = None
        if parent_id:
            parent = await db.get(MemoryTreeNode, parent_id)
            if parent is None or parent.project_id != project_id:
                raise NotFoundError("父节点不存在或不属于当前项目")
            depth = parent.depth + 1
            path = f"{parent.path or '/' + parent.id}/{parent.id}"
            parent.child_count = (parent.child_count or 0) + 1

        content = content_markdown or ""
        node = MemoryTreeNode(
            tenant_id=tenant_id,
            project_id=project_id,
            tree_layer=tree_layer,
            status=NodeStatus.ACTIVE.value,
            parent_id=parent_id,
            depth=depth,
            path=path,
            order_index=order_index,
            title=title,
            content_markdown=content_markdown,
            summary=summary,
            topic_id=topic_id,
            topic_label=topic_label,
            entity_refs_json=_dumps_refs(entity_refs),
            source_episode_id=source_episode_id,
            period_start=period_start,
            period_end=period_end,
            word_count=len(content),
            child_count=0,
            valid_from=valid_from or utcnow(),
            source="memory_tree",
        )
        db.add(node)
        await db.flush()
        if path is None:
            node.path = f"/{node.id}"
            await db.flush()
        return node

    # ---------------- 读取 ----------------
    @staticmethod
    async def get_node(db: AsyncSession, project_id: str, node_id: str) -> MemoryTreeNode:
        node = await db.get(MemoryTreeNode, node_id)
        if node is None or node.project_id != project_id:
            raise NotFoundError("记忆树节点不存在")
        return node

    @staticmethod
    async def list_nodes(
        db: AsyncSession,
        project_id: str,
        *,
        tree_layer: Optional[str] = None,
        parent_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
        include_expired: bool = False,
    ) -> List[MemoryTreeNode]:
        from core.temporal.engine import TemporalEngine

        stmt = select(MemoryTreeNode).where(MemoryTreeNode.project_id == project_id)
        if tree_layer:
            stmt = stmt.where(MemoryTreeNode.tree_layer == tree_layer)
        if parent_id is not None:
            stmt = stmt.where(MemoryTreeNode.parent_id == parent_id)
        stmt = TemporalEngine.apply_temporal_filter(
            stmt, MemoryTreeNode, as_of=as_of, include_expired=include_expired
        )
        stmt = stmt.order_by(MemoryTreeNode.order_index.asc(), MemoryTreeNode.created_at.asc())
        return list((await db.scalars(stmt)).all())

    @classmethod
    async def get_tree(
        cls,
        db: AsyncSession,
        project_id: str,
        tree_layer: str,
        as_of: Optional[datetime] = None,
    ) -> List[dict]:
        """装配某层的完整树形结构（dict，children 嵌套）。"""
        nodes = await cls.list_nodes(
            db, project_id, tree_layer=tree_layer, as_of=as_of
        )
        by_id: dict[str, dict] = {}
        roots: List[dict] = []
        for n in nodes:
            d = node_to_dict(n)
            d["children"] = []
            by_id[n.id] = d
        for n in nodes:
            d = by_id[n.id]
            if n.parent_id and n.parent_id in by_id:
                by_id[n.parent_id]["children"].append(d)
            else:
                roots.append(d)
        return roots

    # ---------------- 更新（带版本快照）----------------
    @classmethod
    async def update_node(
        cls,
        db: AsyncSession,
        project_id: str,
        node_id: str,
        *,
        changed_by: Optional[str] = None,
        title: Optional[str] = None,
        content_markdown: Optional[str] = None,
        summary: Optional[str] = None,
        status: Optional[str] = None,
        parent_id: Optional[str] = None,
        topic_label: Optional[str] = None,
        entity_refs: Optional[List[str]] = None,
        order_index: Optional[int] = None,
        change_summary: Optional[str] = None,
    ) -> MemoryTreeNode:
        node = await cls.get_node(db, project_id, node_id)

        # 快照旧版本
        snapshot = MemoryTreeNodeVersion(
            node_id=node.id,
            tenant_id=node.tenant_id,
            project_id=node.project_id,
            version_number=node.version,
            title=node.title,
            content_markdown=node.content_markdown,
            content_object_key=node.content_object_key,
            changed_by=changed_by,
            change_summary=change_summary,
        )
        db.add(snapshot)

        if title is not None:
            node.title = title
        if content_markdown is not None:
            node.content_markdown = content_markdown
            node.word_count = len(content_markdown)
        if summary is not None:
            node.summary = summary
        if status is not None:
            node.status = status
        if topic_label is not None:
            node.topic_label = topic_label
        if entity_refs is not None:
            node.entity_refs_json = _dumps_refs(entity_refs)
        if order_index is not None:
            node.order_index = order_index
        if parent_id is not None and parent_id != node.parent_id:
            await cls._reparent(db, node, parent_id, project_id)

        node.version += 1  # 时序版本递增
        await db.flush()
        return node

    @staticmethod
    async def _reparent(
        db: AsyncSession, node: MemoryTreeNode, new_parent_id: str, project_id: str
    ) -> None:
        if new_parent_id == node.id:
            raise MemoryTreeError("不能将节点挂载到自身")
        new_parent = await db.get(MemoryTreeNode, new_parent_id)
        if new_parent is None or new_parent.project_id != project_id:
            raise NotFoundError("目标父节点不存在")
        if node.parent_id:
            old_parent = await db.get(MemoryTreeNode, node.parent_id)
            if old_parent:
                old_parent.child_count = max(0, (old_parent.child_count or 1) - 1)
        new_parent.child_count = (new_parent.child_count or 0) + 1
        node.parent_id = new_parent_id
        node.depth = new_parent.depth + 1
        node.path = f"{new_parent.path or '/' + new_parent.id}/{new_parent.id}"

    # ---------------- 删除 ----------------
    @classmethod
    async def delete_node(
        cls, db: AsyncSession, project_id: str, node_id: str, cascade: bool = True
    ) -> int:
        node = await cls.get_node(db, project_id, node_id)
        deleted = 0
        if cascade:
            children = await cls.list_nodes(db, project_id, parent_id=node.id)
            for child in children:
                deleted += await cls.delete_node(db, project_id, child.id, cascade=True)
        if node.parent_id:
            parent = await db.get(MemoryTreeNode, node.parent_id)
            if parent:
                parent.child_count = max(0, (parent.child_count or 1) - 1)
        await db.delete(node)
        await db.flush()
        return deleted + 1

    # ---------------- 版本 ----------------
    @staticmethod
    async def list_versions(
        db: AsyncSession, project_id: str, node_id: str
    ) -> List[MemoryTreeNodeVersion]:
        stmt = (
            select(MemoryTreeNodeVersion)
            .where(
                MemoryTreeNodeVersion.node_id == node_id,
                MemoryTreeNodeVersion.project_id == project_id,
            )
            .order_by(MemoryTreeNodeVersion.version_number.desc())
        )
        return list((await db.scalars(stmt)).all())

    @classmethod
    async def rollback(
        cls,
        db: AsyncSession,
        project_id: str,
        node_id: str,
        version_number: int,
        changed_by: Optional[str] = None,
    ) -> MemoryTreeNode:
        versions = await cls.list_versions(db, project_id, node_id)
        target = next((v for v in versions if v.version_number == version_number), None)
        if target is None:
            raise NotFoundError("目标版本不存在")
        return await cls.update_node(
            db,
            project_id,
            node_id,
            changed_by=changed_by,
            title=target.title,
            content_markdown=target.content_markdown,
            change_summary=f"rollback to v{version_number}",
        )


memory_tree_service = MemoryTreeService()
