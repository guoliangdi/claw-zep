"""
PostgreSQL 图谱仓储（时序感知）
================================
基于 GraphEntityMeta / GraphRelationMeta 镜像表提供图遍历能力。
之所以在 PG 镜像上做遍历而非仅依赖 Kuzu：镜像表挂载了完整双时序字段，
可在『任意时间点』做快照式邻居/路径查询，满足 Palantir 因果推演与时序回溯。

Kuzu 仍由 Graphiti 写入并可承担大规模原生图算法（见 KuzuAdapter）。
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.temporal.engine import TemporalEngine
from models.graph import GraphEntityMeta, GraphRelationMeta


def _pid_cond(model, project_id):
    """project_id 过滤：单值=隔离，列表=融合（项目组联合）。"""
    if isinstance(project_id, (list, tuple, set)):
        return model.project_id.in_(list(project_id))
    return model.project_id == project_id


class PGGraphRepository:
    # ---------------- 实体 ----------------
    @staticmethod
    async def find_entities_by_name(
        db: AsyncSession,
        project_id: str,
        name: str,
        as_of: Optional[datetime] = None,
        limit: int = 10,
    ) -> List[GraphEntityMeta]:
        stmt = select(GraphEntityMeta).where(
            _pid_cond(GraphEntityMeta, project_id),
            GraphEntityMeta.name.ilike(f"%{name}%"),
        )
        stmt = TemporalEngine.apply_temporal_filter(stmt, GraphEntityMeta, as_of=as_of)
        return list((await db.scalars(stmt.limit(limit))).all())

    @staticmethod
    async def get_entity_by_uuid(
        db: AsyncSession, project_id: str, kuzu_uuid: str, as_of: Optional[datetime] = None
    ) -> Optional[GraphEntityMeta]:
        stmt = select(GraphEntityMeta).where(
            _pid_cond(GraphEntityMeta, project_id),
            GraphEntityMeta.kuzu_uuid == kuzu_uuid,
        )
        stmt = TemporalEngine.apply_temporal_filter(stmt, GraphEntityMeta, as_of=as_of)
        return await db.scalar(stmt.order_by(GraphEntityMeta.version.desc()).limit(1))

    # ---------------- 关系 ----------------
    @staticmethod
    async def _active_relations(
        db: AsyncSession, project_id: str, as_of: Optional[datetime] = None
    ) -> List[GraphRelationMeta]:
        stmt = select(GraphRelationMeta).where(_pid_cond(GraphRelationMeta, project_id))
        stmt = TemporalEngine.apply_temporal_filter(stmt, GraphRelationMeta, as_of=as_of)
        return list((await db.scalars(stmt)).all())

    @classmethod
    async def neighbors(
        cls,
        db: AsyncSession,
        project_id: str,
        entity_uuid: str,
        as_of: Optional[datetime] = None,
        direction: str = "both",
    ) -> List[Tuple[GraphRelationMeta, str]]:
        """返回 (关系, 邻居uuid) 列表。direction: out|in|both。"""
        rels = await cls._active_relations(db, project_id, as_of)
        out = []
        for r in rels:
            if direction in ("out", "both") and r.source_entity_kuzu_uuid == entity_uuid:
                out.append((r, r.target_entity_kuzu_uuid))
            if direction in ("in", "both") and r.target_entity_kuzu_uuid == entity_uuid:
                out.append((r, r.source_entity_kuzu_uuid))
        return out

    @classmethod
    async def find_paths(
        cls,
        db: AsyncSession,
        project_id: str,
        start_uuid: str,
        max_hops: int = 3,
        max_paths: int = 20,
        as_of: Optional[datetime] = None,
    ) -> List[List[dict]]:
        """
        从起点 BFS 枚举因果传导路径（沿关系方向）。
        返回路径列表，每条路径是 [{from,to,relation,fact,confidence}] 边序列。
        """
        rels = await cls._active_relations(db, project_id, as_of)
        adj: Dict[str, List[GraphRelationMeta]] = defaultdict(list)
        for r in rels:
            adj[r.source_entity_kuzu_uuid].append(r)

        paths: List[List[dict]] = []
        queue: deque = deque()
        queue.append((start_uuid, [], {start_uuid}))
        while queue and len(paths) < max_paths:
            node, edges, visited = queue.popleft()
            if edges:
                paths.append(edges)
            if len(edges) >= max_hops:
                continue
            for r in adj.get(node, []):
                nxt = r.target_entity_kuzu_uuid
                if nxt in visited:
                    continue
                edge = {
                    "from": r.source_entity_kuzu_uuid,
                    "to": nxt,
                    "from_name": r.source_entity_name,
                    "to_name": r.target_entity_name,
                    "relation": r.relation_type,
                    "fact": r.fact,
                    "confidence": r.confidence_score,
                }
                queue.append((nxt, edges + [edge], visited | {nxt}))
        return [p for p in paths if p]

    # ---------------- 可视化 ----------------
    @classmethod
    async def visualization(
        cls,
        db: AsyncSession,
        project_id: str,
        as_of: Optional[datetime] = None,
        limit: int = 500,
    ) -> dict:
        """返回 Cytoscape 友好的 {nodes, edges}。"""
        ent_stmt = select(GraphEntityMeta).where(_pid_cond(GraphEntityMeta, project_id))
        ent_stmt = TemporalEngine.apply_temporal_filter(ent_stmt, GraphEntityMeta, as_of=as_of)
        entities = list((await db.scalars(ent_stmt.limit(limit))).all())
        relations = await cls._active_relations(db, project_id, as_of)

        import json as _json

        def _attrs(e):
            try:
                return _json.loads(e.attributes_json) if e.attributes_json else {}
            except Exception:
                return {}

        nodes = [
            {
                "id": e.kuzu_uuid,
                "label": e.name,
                "type": e.entity_type,
                "summary": e.summary,
                "attributes": _attrs(e),
                "valid_from": e.valid_from,
                "valid_until": e.valid_until,
            }
            for e in entities
        ]
        node_ids = {n["id"] for n in nodes}
        edges = [
            {
                "id": r.kuzu_uuid,
                "source": r.source_entity_kuzu_uuid,
                "target": r.target_entity_kuzu_uuid,
                "label": r.relation_type,
                "fact": r.fact,
                "confidence_score": r.confidence_score,
                "valid_from": r.valid_from,
                "valid_until": r.valid_until,
            }
            for r in relations
            if r.source_entity_kuzu_uuid in node_ids and r.target_entity_kuzu_uuid in node_ids
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }


pg_graph_repo = PGGraphRepository()
