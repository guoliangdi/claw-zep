"""
结构化直灌服务
==============
worldmonitor 等上游推送『已抽好的实体+关系三元组』，本服务只做：
  时序打标 → 镜像表 + AGE 图 + pgvector 三库落地（复用 orchestrator 写入逻辑），
  **不调用 LLM**。一条 record = 一个源文档（生成一个 Episode 留存溯源）。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.extractors import ExtractedEntity, ExtractedRelation, ExtractionResult
from core.services.graphiti_orchestrator import graphiti_orchestrator
from models.graph import Episode, EpisodeStatus, EpisodeType
from models.project import Project
from schemas.ingest import BulkIngestRequest, BulkIngestResponse

logger = structlog.get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ingest_bulk(
    db: AsyncSession, project: Project, req: BulkIngestRequest
) -> BulkIngestResponse:
    start = time.perf_counter()
    orch = graphiti_orchestrator
    total_e = total_r = total_ep = 0

    for record in req.records:
        ref_time = record.valid_from or req.default_valid_from or utcnow()

        episode = Episode(
            tenant_id=project.tenant_id,
            project_id=project.id,
            name=record.name,
            content=record.text or "(structured ingest)",
            episode_type=EpisodeType.FACT_TRIPLE.value,
            source=req.source,
            group_id=req.group_id,
            status=EpisodeStatus.COMPLETED.value,
            valid_from=ref_time,
        )
        if record.source_ref:
            episode.source_description = json.dumps(record.source_ref, ensure_ascii=False)[:256]
        db.add(episode)
        await db.flush()
        total_ep += 1

        # 构造 ExtractionResult（复用 orchestrator 同一套写入：时序/AGE/向量/去重）
        result = ExtractionResult(extractor=f"bulk:{req.source}")
        name2ent: dict[str, ExtractedEntity] = {}
        for be in record.entities:
            ee = ExtractedEntity(
                name=be.name, entity_type=be.entity_type,
                summary=be.summary, attributes=be.attributes,
            )
            result.entities.append(ee)
            name2ent[be.name] = ee
        for br in record.relations:
            src = name2ent.get(br.source)
            tgt = name2ent.get(br.target)
            if not (src and tgt):
                logger.warning("bulk relation refers unknown entity",
                               source=br.source, target=br.target)
                continue
            result.relations.append(ExtractedRelation(
                source_uuid=src.uuid, target_uuid=tgt.uuid,
                relation_type=br.relation_type, fact=br.fact,
                source_name=src.name, target_name=tgt.name,
                confidence=br.confidence, valid_at=br.valid_from or ref_time,
            ))

        ne, nr = await orch.persist_structured(db, episode, project, result, ref_time)
        episode.extracted_entity_count = ne
        episode.extracted_relation_count = nr
        total_e += ne
        total_r += nr

        if req.build_memory_tree and orch.memory_tree_hook is not None:
            try:
                await orch.memory_tree_hook(db, episode, result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("bulk memory_tree hook failed", error=str(exc))

    await orch._refresh_project_counts(db, project)
    await db.flush()

    elapsed = (time.perf_counter() - start) * 1000
    logger.info("bulk ingest done", source=req.source, project_id=project.id,
                records=len(req.records), entities=total_e, relations=total_r)
    return BulkIngestResponse(
        source=req.source, project_id=project.id,
        records=len(req.records), episodes=total_ep,
        entities=total_e, relations=total_r, elapsed_ms=round(elapsed, 2),
    )
