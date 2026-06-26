"""
Graphiti 调度封装
==================
claw-zep 的写入核心。复用原生 Graphiti 抽取能力（或离线启发式降级），
统一接管：
  · 租户/项目隔离（group_id = project_id）
  · 双时序打标（valid_from / version，经 TemporalEngine）
  · 分发写入三大存储：
      - 图谱：Kuzu（由 Graphiti 原生写入）+ PostgreSQL 镜像元数据（本模块）
      - 向量：Chroma（经 VectorAdapter，Phase 7 注入，缺省跳过）
      - 记忆树 SourceTree：经 memory_tree 模块（Phase 6 注入，缺省跳过）

设计为不重构 Graphiti 内核，仅在其外层做调度与落库镜像。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.services.extractors import (
    Extractor,
    ExtractionResult,
    HeuristicExtractor,
)
from core.temporal.engine import TemporalEngine
from models.graph import (
    Episode,
    EpisodeStatus,
    GraphEntityMeta,
    GraphRelationMeta,
)
from models.project import Project

logger = structlog.get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GraphitiOrchestrator:
    """每进程单例；按项目惰性构建 Graphiti 实例。"""

    def __init__(self) -> None:
        self._graphiti_cache: dict[str, Any] = {}
        self._heuristic = HeuristicExtractor()
        # 存储适配器（按 STORAGE_BACKEND 选择）与记忆树钩子
        from core.adapters import get_vector_adapter, get_age_adapter

        self.vector_adapter: Optional[Any] = get_vector_adapter()
        self.age_adapter: Optional[Any] = get_age_adapter()
        self.memory_tree_hook: Optional[Callable] = self._default_memory_tree_hook

    def _age_on(self) -> bool:
        return settings.storage_backend == "postgres" and settings.age_enabled

    @staticmethod
    async def _default_memory_tree_hook(db: AsyncSession, episode: Any, result: Any) -> None:
        """默认记忆树钩子：为 Episode 生成 SourceTree 节点。"""
        from core.memory_tree.builder import memory_tree_builder

        await memory_tree_builder.build_source_node(db, episode, result)

    # ---------------- Graphiti 实例 ----------------
    def _build_graphiti(self, project: Project) -> Optional[Any]:
        """构建并缓存项目专属 Graphiti（基于 Kuzu 驱动）。失败返回 None。"""
        if project.id in self._graphiti_cache:
            return self._graphiti_cache[project.id]
        try:
            from graphiti_core import Graphiti
            from graphiti_core.driver.kuzu_driver import KuzuDriver

            db_path = f"{settings.kuzu_db_path}/{project.kuzu_graph_name}"
            driver = KuzuDriver(db=db_path)
            gi = Graphiti(graph_driver=driver)
            self._graphiti_cache[project.id] = gi
            return gi
        except Exception as exc:  # noqa: BLE001
            logger.warning("graphiti unavailable, fallback to heuristic", error=str(exc))
            return None

    def _select_extractor(self, project: Project) -> Extractor:
        if settings.graphiti_entity_extraction_enabled and (settings.llm_api_key):
            gi = self._build_graphiti(project)
            if gi is not None:
                from core.services.extractors import GraphitiExtractor

                return GraphitiExtractor(gi, group_id=project.id)
        return self._heuristic

    # ---------------- 实体逻辑键解析 ----------------
    @staticmethod
    async def _resolve_entity_kuzu_uuid(
        db: AsyncSession, project_id: str, name: str, entity_type: str, fallback_uuid: str
    ) -> str:
        """
        将同名同类型实体映射到稳定 kuzu_uuid（支撑时序去重/版本演进）。
        已存在则复用其 kuzu_uuid，否则用抽取产生的 uuid。
        """
        existing = await db.scalar(
            select(GraphEntityMeta.kuzu_uuid)
            .where(
                GraphEntityMeta.project_id == project_id,
                GraphEntityMeta.name == name,
                GraphEntityMeta.entity_type == entity_type,
            )
            .limit(1)
        )
        return existing or fallback_uuid

    # ---------------- 主流程 ----------------
    async def ingest_episode(self, db: AsyncSession, episode_id: str) -> dict:
        """处理单条 Episode：抽取 → 时序打标 → 落库镜像 → 更新统计。"""
        episode = await db.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"episode not found: {episode_id}")

        project = await db.get(Project, episode.project_id)
        if project is None:
            raise ValueError(f"project not found: {episode.project_id}")

        episode.status = EpisodeStatus.PROCESSING.value
        await db.flush()

        reference_time = episode.valid_from or utcnow()
        try:
            extractor = self._select_extractor(project)
            ontology = json.loads(project.ontology_json) if project.ontology_json else None
            result: ExtractionResult = await extractor.extract(
                episode.content, reference_time, ontology
            )

            entity_uuid_map = await self._persist_entities(
                db, episode, project, result, reference_time
            )
            rel_count = await self._persist_relations(
                db, episode, project, result, reference_time, entity_uuid_map
            )

            episode.extracted_entity_count = len(result.entities)
            episode.extracted_relation_count = rel_count
            episode.status = EpisodeStatus.COMPLETED.value
            episode.graphiti_uuid = episode.graphiti_uuid or None

            await self._refresh_project_counts(db, project)
            await db.flush()

            # 可选：记忆树 SourceTree 钩子
            if self.memory_tree_hook is not None:
                try:
                    await self.memory_tree_hook(db, episode, result)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("memory_tree hook failed", error=str(exc))

            logger.info(
                "episode ingested",
                episode_id=episode.id,
                extractor=result.extractor,
                entities=len(result.entities),
                relations=rel_count,
            )
            return {
                "episode_id": episode.id,
                "status": episode.status,
                "extractor": result.extractor,
                "entities": len(result.entities),
                "relations": rel_count,
            }
        except Exception as exc:  # noqa: BLE001
            episode.status = EpisodeStatus.FAILED.value
            episode.error_message = str(exc)[:2000]
            await db.flush()
            logger.error("episode ingest failed", episode_id=episode.id, error=str(exc))
            raise

    async def persist_structured(
        self,
        db: AsyncSession,
        episode: Episode,
        project: Project,
        result: ExtractionResult,
        reference_time: datetime,
    ) -> tuple[int, int]:
        """
        公开入口：把一份 ExtractionResult 落地到三库（时序+图+向量），跳过抽取。
        供结构化直灌(bulk)复用 LLM 路径同一套写入逻辑。返回 (实体数, 关系数)。
        """
        uuid_map = await self._persist_entities(db, episode, project, result, reference_time)
        rel_count = await self._persist_relations(
            db, episode, project, result, reference_time, uuid_map
        )
        return len(result.entities), rel_count

    async def _persist_entities(
        self,
        db: AsyncSession,
        episode: Episode,
        project: Project,
        result: ExtractionResult,
        reference_time: datetime,
    ) -> dict[str, str]:
        """写入实体镜像（时序 supersede）。返回 {抽取uuid: 稳定kuzu_uuid}。"""
        uuid_map: dict[str, str] = {}
        for ent in result.entities:
            kuzu_uuid = await self._resolve_entity_kuzu_uuid(
                db, project.id, ent.name, ent.entity_type, ent.uuid
            )
            uuid_map[ent.uuid] = kuzu_uuid
            await TemporalEngine.supersede(
                db,
                GraphEntityMeta,
                logical_key="kuzu_uuid",
                logical_value=kuzu_uuid,
                project_id=project.id,
                new_attrs={
                    "tenant_id": episode.tenant_id,
                    "name": ent.name,
                    "entity_type": ent.entity_type,
                    "summary": ent.summary,
                    "attributes_json": (
                        json.dumps(ent.attributes, ensure_ascii=False)
                        if getattr(ent, "attributes", None) else None
                    ),
                    "graphiti_uuid": ent.uuid,
                    "source_episode_id": episode.id,
                },
                valid_from=reference_time,
                source=f"graphiti_extract:{result.extractor}",
            )
            # 向量写入（同事务；即使无摘要也以名称建索引，保证语义召回可用）
            if self.vector_adapter is not None:
                try:
                    await self.vector_adapter.upsert_entity(
                        project, kuzu_uuid, ent.name, ent.summary or ent.name,
                        episode.tenant_id, session=db,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("vector upsert failed", error=str(exc))
            # AGE 图投影（同事务，当前状态）
            if self._age_on():
                try:
                    await self.age_adapter.upsert_entity(
                        project.id, kuzu_uuid, ent.name, ent.entity_type,
                        valid_from=reference_time, session=db,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AGE entity projection failed", error=str(exc))
        return uuid_map

    async def _persist_relations(
        self,
        db: AsyncSession,
        episode: Episode,
        project: Project,
        result: ExtractionResult,
        reference_time: datetime,
        entity_uuid_map: dict[str, str],
    ) -> int:
        count = 0
        for rel in result.relations:
            src = entity_uuid_map.get(rel.source_uuid, rel.source_uuid)
            tgt = entity_uuid_map.get(rel.target_uuid, rel.target_uuid)
            # 关系逻辑键：source|type|target 组合，保证同一三元组版本演进
            rel_logical = f"{src}|{rel.relation_type}|{tgt}"
            await TemporalEngine.supersede(
                db,
                GraphRelationMeta,
                logical_key="kuzu_uuid",
                logical_value=rel_logical,
                project_id=project.id,
                new_attrs={
                    "tenant_id": episode.tenant_id,
                    "relation_type": rel.relation_type,
                    "fact": rel.fact,
                    "source_entity_kuzu_uuid": src,
                    "target_entity_kuzu_uuid": tgt,
                    "source_entity_name": rel.source_name,
                    "target_entity_name": rel.target_name,
                    "confidence_score": rel.confidence,
                    "graphiti_uuid": rel.uuid,
                    "source_episode_id": episode.id,
                },
                valid_from=rel.valid_at or reference_time,
                source=f"graphiti_extract:{result.extractor}",
            )
            # AGE 图投影（同事务，当前状态）
            if self._age_on():
                try:
                    await self.age_adapter.upsert_relation(
                        project.id, rel.relation_type, src, tgt,
                        fact=rel.fact, confidence=rel.confidence,
                        valid_from=rel.valid_at or reference_time, session=db,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AGE relation projection failed", error=str(exc))
            count += 1
        return count

    @staticmethod
    async def _refresh_project_counts(db: AsyncSession, project: Project) -> None:
        active = TemporalEngine.active_conditions
        project.entity_count = await db.scalar(
            select(func.count())
            .select_from(GraphEntityMeta)
            .where(GraphEntityMeta.project_id == project.id, *active(GraphEntityMeta))
        ) or 0
        project.relation_count = await db.scalar(
            select(func.count())
            .select_from(GraphRelationMeta)
            .where(GraphRelationMeta.project_id == project.id, *active(GraphRelationMeta))
        ) or 0
        project.episode_count = await db.scalar(
            select(func.count()).select_from(Episode).where(Episode.project_id == project.id)
        ) or 0


# 进程级单例
graphiti_orchestrator = GraphitiOrchestrator()
