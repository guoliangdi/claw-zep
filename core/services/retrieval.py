"""
统一混合检索服务
================
检索管线（对标 Zep + Palantir 双形态）：

  常规检索 search():
     时序过滤 → 向量语义召回(实体) → 图谱关系链路扩展 → 记忆树摘要加权 → 重排

  推演检索 reason():
     问题 → 种子实体识别 → 因果链路 BFS → 子图可视化 → 记忆树证据 → LLM 综合结论

全程 as_of 时序过滤，支持任意时间点的快照式检索与推演。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.chroma_adapter import chroma_adapter
from core.adapters.graph_repo import pg_graph_repo
from core.temporal.engine import TemporalEngine
from models.graph import GraphEntityMeta, GraphRelationMeta
from models.memory_tree import MemoryTreeNode
from models.project import Project
from schemas.memory import SearchRequest, SearchResponse, SearchResultItem
from schemas.palantir import (
    CausalPath,
    CausalPathEdge,
    CausalPathNode,
    MemoryTreeEvidence,
    ReasoningRequest,
    ReasoningResponse,
)

logger = structlog.get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RetrievalService:
    # ============== 常规检索 ==============
    @classmethod
    async def search(
        cls, db: AsyncSession, project: Project, req: SearchRequest,
        project_ids: Optional[List[str]] = None,
    ) -> SearchResponse:
        start = time.perf_counter()
        as_of = req.as_of
        # 隔离/融合：project_ids 为 None 时仅当前项目（隔离）；列表则为融合范围
        pids = project_ids or [project.id]
        results: List[SearchResultItem] = []

        entity_scores: Dict[str, float] = {}
        if req.search_entities:
            entity_scores = await cls._vector_recall_entities(project, req, pids)

        # 图谱链路扩展：对召回实体的邻居加权（关系强度传播）
        if req.search_relations and entity_scores:
            await cls._expand_via_graph(db, pids, entity_scores, as_of)

        # 实体结果落库校验 + 时序过滤
        entity_items, entity_objs = await cls._materialize_entities(
            db, pids, entity_scores, as_of, req.vector_weight + req.graph_weight
        )
        results.extend(entity_items)

        # 记忆树召回（标题/正文/摘要文本匹配 + 加权）
        if req.search_memory_tree:
            tree_items = await cls._recall_memory_tree(
                db, pids, req.query, as_of, req.limit, req.tree_weight
            )
            results.extend(tree_items)

        results.sort(key=lambda r: r.score, reverse=True)
        results = results[: req.limit]

        elapsed = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=req.query,
            results=results,
            total=len(results),
            elapsed_ms=round(elapsed, 2),
        )

    @staticmethod
    async def _vector_recall_entities(
        project: Project, req: SearchRequest, project_ids: List[str]
    ) -> Dict[str, float]:
        from core.adapters import get_vector_adapter

        hits = await get_vector_adapter().query(
            project.chroma_collection_name,
            req.query,
            n_results=max(req.limit * 3, 20),
            where={"kind": "entity", "project_id": project_ids},
        )
        scores: Dict[str, float] = {}
        for h in hits:
            kuzu_uuid = (h.get("metadata") or {}).get("kuzu_uuid")
            if kuzu_uuid:
                scores[kuzu_uuid] = max(scores.get(kuzu_uuid, 0.0), float(h.get("score", 0.0)))
        return scores

    @staticmethod
    async def _expand_via_graph(
        db: AsyncSession,
        project_ids: List[str],
        entity_scores: Dict[str, float],
        as_of: Optional[datetime],
        decay: float = 0.4,
    ) -> None:
        seeds = list(entity_scores.items())
        for uuid, score in seeds:
            neighbors = await pg_graph_repo.neighbors(db, project_ids, uuid, as_of=as_of)
            for _rel, nbr_uuid in neighbors:
                propagated = score * decay
                if propagated > entity_scores.get(nbr_uuid, 0.0):
                    entity_scores[nbr_uuid] = propagated

    @staticmethod
    async def _materialize_entities(
        db: AsyncSession,
        project_ids: List[str],
        entity_scores: Dict[str, float],
        as_of: Optional[datetime],
        weight: float,
    ) -> tuple[List[SearchResultItem], List[GraphEntityMeta]]:
        items: List[SearchResultItem] = []
        objs: List[GraphEntityMeta] = []
        if not entity_scores:
            return items, objs
        stmt = select(GraphEntityMeta).where(
            GraphEntityMeta.project_id.in_(project_ids),
            GraphEntityMeta.kuzu_uuid.in_(list(entity_scores.keys())),
        )
        stmt = TemporalEngine.apply_temporal_filter(stmt, GraphEntityMeta, as_of=as_of)
        rows = (await db.scalars(stmt)).all()
        seen = set()
        for e in rows:
            if e.kuzu_uuid in seen:
                continue
            seen.add(e.kuzu_uuid)
            objs.append(e)
            items.append(
                SearchResultItem(
                    kind="entity",
                    id=e.kuzu_uuid,
                    score=round(entity_scores.get(e.kuzu_uuid, 0.0) * max(weight, 0.01), 4),
                    title=e.name,
                    content=e.summary,
                    valid_from=e.valid_from,
                    valid_until=e.valid_until,
                    metadata={"entity_type": e.entity_type, "version": e.version},
                )
            )
        return items, objs

    @staticmethod
    async def _recall_memory_tree(
        db: AsyncSession,
        project_ids: List[str],
        query: str,
        as_of: Optional[datetime],
        limit: int,
        weight: float,
    ) -> List[SearchResultItem]:
        terms = [t for t in query.split() if t]
        stmt = select(MemoryTreeNode).where(MemoryTreeNode.project_id.in_(project_ids))
        if terms:
            conds = []
            for t in terms:
                like = f"%{t}%"
                conds.append(MemoryTreeNode.title.ilike(like))
                conds.append(MemoryTreeNode.content_markdown.ilike(like))
                conds.append(MemoryTreeNode.summary.ilike(like))
            stmt = stmt.where(or_(*conds))
        stmt = TemporalEngine.apply_temporal_filter(stmt, MemoryTreeNode, as_of=as_of)
        rows = (await db.scalars(stmt.limit(limit * 2))).all()

        items: List[SearchResultItem] = []
        for n in rows:
            hay = f"{n.title} {n.summary or ''} {n.content_markdown or ''}".lower()
            match = sum(hay.count(t.lower()) for t in terms) if terms else 1
            base = min(1.0, 0.3 + 0.1 * match)
            items.append(
                SearchResultItem(
                    kind="memory_tree",
                    id=n.id,
                    score=round(base * max(weight, 0.01), 4),
                    title=n.title,
                    content=n.summary or (n.content_markdown or "")[:200],
                    valid_from=n.valid_from,
                    valid_until=n.valid_until,
                    metadata={"tree_layer": n.tree_layer},
                )
            )
        items.sort(key=lambda r: r.score, reverse=True)
        return items[:limit]

    # ============== 推演检索（Palantir）==============
    @classmethod
    async def reason(
        cls, db: AsyncSession, project: Project, req: ReasoningRequest,
        project_ids: Optional[List[str]] = None,
    ) -> ReasoningResponse:
        start = time.perf_counter()
        as_of = req.as_of
        pids = project_ids or [project.id]

        # 1. 种子实体：向量召回 + 名称匹配
        search_req = SearchRequest(
            query=req.question, limit=8, as_of=as_of,
            search_entities=True, search_relations=False, search_memory_tree=False,
        )
        seed_scores = await cls._vector_recall_entities(project, search_req, pids)
        seed_items, seed_objs = await cls._materialize_entities(
            db, pids, seed_scores, as_of, 1.0
        )
        # 名称直配补充
        for term in [w for w in req.question.split() if len(w) >= 2]:
            for e in await pg_graph_repo.find_entities_by_name(db, pids, term, as_of, 3):
                if all(s.kuzu_uuid != e.kuzu_uuid for s in seed_objs):
                    seed_objs.append(e)

        seed_nodes = [
            CausalPathNode(kuzu_uuid=e.kuzu_uuid, name=e.name, entity_type=e.entity_type)
            for e in seed_objs[:6]
        ]

        # 2. 因果链路 BFS
        causal_paths: List[CausalPath] = []
        involved_uuids: set = set()
        for seed in seed_nodes:
            raw_paths = await pg_graph_repo.find_paths(
                db, pids, seed.kuzu_uuid,
                max_hops=req.max_hops, max_paths=req.max_paths, as_of=as_of,
            )
            for rp in raw_paths:
                nodes, edges = cls._path_to_schema(rp)
                involved_uuids.update(e["from"] for e in rp)
                involved_uuids.update(e["to"] for e in rp)
                causal_paths.append(
                    CausalPath(
                        nodes=nodes, edges=edges,
                        score=round(sum((e.get("confidence") or 0.5) for e in rp) / len(rp), 3),
                        narrative=cls._narrate_path(rp),
                    )
                )
        causal_paths.sort(key=lambda p: p.score, reverse=True)
        causal_paths = causal_paths[: req.max_paths]

        # 3. 子图可视化
        viz = await pg_graph_repo.visualization(db, pids, as_of=as_of)
        from schemas.graph import GraphVisualization, GraphNode, GraphEdge

        sub_nodes = [GraphNode(**n) for n in viz["nodes"] if n["id"] in involved_uuids] or [
            GraphNode(**n) for n in viz["nodes"][:30]
        ]
        sub_node_ids = {n.id for n in sub_nodes}
        sub_edges = [
            GraphEdge(**e) for e in viz["edges"]
            if e["source"] in sub_node_ids and e["target"] in sub_node_ids
        ]
        graph_viz = GraphVisualization(
            nodes=sub_nodes, edges=sub_edges,
            node_count=len(sub_nodes), edge_count=len(sub_edges),
        )

        # 4. 记忆树证据
        evidence: List[MemoryTreeEvidence] = []
        if req.include_memory_tree:
            tree_items = await cls._recall_memory_tree(
                db, pids, req.question, as_of, 5, 1.0
            )
            evidence = [
                MemoryTreeEvidence(
                    node_id=t.id, title=t.title,
                    excerpt=(t.content or "")[:200], score=t.score,
                )
                for t in tree_items
            ]

        # 5. 综合结论
        answer = await cls._synthesize_answer(req.question, causal_paths, evidence, seed_nodes)

        elapsed = (time.perf_counter() - start) * 1000
        return ReasoningResponse(
            question=req.question,
            answer=answer,
            as_of=as_of,
            seed_entities=seed_nodes,
            causal_paths=causal_paths,
            graph=graph_viz,
            evidence=evidence,
            elapsed_ms=round(elapsed, 2),
        )

    @staticmethod
    def _path_to_schema(rp: List[dict]):
        nodes: List[CausalPathNode] = []
        edges: List[CausalPathEdge] = []
        seen = set()
        for e in rp:
            for uuid, name in ((e["from"], e.get("from_name")), (e["to"], e.get("to_name"))):
                if uuid not in seen:
                    seen.add(uuid)
                    nodes.append(CausalPathNode(kuzu_uuid=uuid, name=name or uuid, entity_type="Entity"))
            edges.append(
                CausalPathEdge(
                    relation_type=e["relation"], fact=e.get("fact"),
                    confidence_score=e.get("confidence"),
                )
            )
        return nodes, edges

    @staticmethod
    def _narrate_path(rp: List[dict]) -> str:
        parts = []
        for e in rp:
            parts.append(
                f"{e.get('from_name') or e['from']} —[{e['relation']}]→ {e.get('to_name') or e['to']}"
            )
        return " ; ".join(parts)

    @staticmethod
    async def _synthesize_answer(
        question: str,
        paths: List[CausalPath],
        evidence: List[MemoryTreeEvidence],
        seeds: List[CausalPathNode],
    ) -> str:
        from core.config import settings

        path_text = "\n".join(f"- {p.narrative}（置信 {p.score}）" for p in paths[:10])
        ev_text = "\n".join(f"- {e.title}: {e.excerpt}" for e in evidence[:5])
        seed_text = "、".join(s.name for s in seeds) or "（未识别到明确实体）"

        if not settings.llm_api_key:
            # 离线启发式结论
            lines = [f"针对问题「{question}」的因果推演："]
            lines.append(f"识别核心实体：{seed_text}。")
            if paths:
                lines.append(f"发现 {len(paths)} 条传导链路，主要路径：")
                lines.append(path_text)
            else:
                lines.append("未在当前知识图谱中发现明确的因果传导链路。")
            if evidence:
                lines.append("相关记忆树证据：")
                lines.append(ev_text)
            return "\n".join(lines)

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            prompt = (
                f"你是企业知识推演专家。基于以下因果链路与证据，回答问题。\n\n"
                f"问题：{question}\n\n核心实体：{seed_text}\n\n"
                f"因果链路：\n{path_text or '（无）'}\n\n证据：\n{ev_text or '（无）'}\n\n"
                f"请给出结构化的因果分析与风险传导结论（中文）。"
            )
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("reason synthesize llm failed", error=str(exc))
            return f"（离线）核心实体：{seed_text}；链路数：{len(paths)}。\n{path_text}"


retrieval_service = RetrievalService()
