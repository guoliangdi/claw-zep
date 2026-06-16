"""
实体/关系抽取器
================
统一抽取结果数据结构 + 两种实现：
  1. GraphitiExtractor  —— 包装原生 Graphiti（LLM 驱动，能力最强）
  2. HeuristicExtractor —— 无外部依赖的轻量启发式抽取（离线/降级可用）

orchestrator 依据配置与可用性选择实现，保证『自主可控』离线亦可运行。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str = "Entity"
    summary: Optional[str] = None
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedRelation:
    source_uuid: str
    target_uuid: str
    relation_type: str
    fact: Optional[str] = None
    source_name: Optional[str] = None
    target_name: Optional[str] = None
    confidence: Optional[float] = None
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    valid_at: Optional[datetime] = None
    invalid_at: Optional[datetime] = None


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    extractor: str = "unknown"


class Extractor(Protocol):
    async def extract(
        self, content: str, reference_time: datetime, ontology: Optional[dict] = None
    ) -> ExtractionResult: ...


# 简单中英文专有名词/大写词候选实体
_CAPWORD = re.compile(r"\b([A-Z][A-Za-z0-9_\-]{2,})\b")
_CJK_TERM = re.compile(r"[一-龥]{2,8}(?:公司|集团|供应商|产品|部门|项目|系统|平台|客户|团队)")
# 关系触发词
_REL_PATTERNS = [
    (re.compile(r"(.{2,20}?)\s*(?:收购|并购|acquired|acquires)\s*(.{2,20})"), "ACQUIRED"),
    (re.compile(r"(.{2,20}?)\s*(?:供应|供货|supplies|supplied)\s*(.{2,20})"), "SUPPLIES"),
    (re.compile(r"(.{2,20}?)\s*(?:依赖|depends on|relies on)\s*(.{2,20})"), "DEPENDS_ON"),
    (re.compile(r"(.{2,20}?)\s*(?:属于|belongs to|part of)\s*(.{2,20})"), "PART_OF"),
    (re.compile(r"(.{2,20}?)\s*(?:影响|impacts|affects)\s*(.{2,20})"), "IMPACTS"),
]


class HeuristicExtractor:
    """无 LLM 依赖的启发式抽取，用于离线/降级。"""

    name = "heuristic"

    async def extract(
        self, content: str, reference_time: datetime, ontology: Optional[dict] = None
    ) -> ExtractionResult:
        result = ExtractionResult(extractor=self.name)
        by_name: dict[str, ExtractedEntity] = {}

        def upsert_entity(name: str, etype: str = "Entity") -> ExtractedEntity:
            name = name.strip()
            if name not in by_name:
                by_name[name] = ExtractedEntity(name=name, entity_type=etype)
            return by_name[name]

        for m in _CJK_TERM.finditer(content):
            upsert_entity(m.group(0), "Organization")
        for m in _CAPWORD.finditer(content):
            token = m.group(1)
            if token.lower() not in {"the", "and", "this", "that", "with"}:
                upsert_entity(token, "Entity")

        # 关系抽取
        for pattern, rtype in _REL_PATTERNS:
            for rm in pattern.finditer(content):
                src = upsert_entity(rm.group(1).strip().split()[-1] if rm.group(1).strip() else "")
                tgt = upsert_entity(rm.group(2).strip().split()[0] if rm.group(2).strip() else "")
                if src.name and tgt.name and src.name != tgt.name:
                    result.relations.append(
                        ExtractedRelation(
                            source_uuid=src.uuid,
                            target_uuid=tgt.uuid,
                            relation_type=rtype,
                            fact=rm.group(0).strip(),
                            source_name=src.name,
                            target_name=tgt.name,
                            confidence=0.5,
                            valid_at=reference_time,
                        )
                    )

        result.entities = list(by_name.values())
        return result


class GraphitiExtractor:
    """包装原生 Graphiti 的 LLM 驱动抽取。"""

    name = "graphiti"

    def __init__(self, graphiti_instance: Any, group_id: str):
        self._graphiti = graphiti_instance
        self._group_id = group_id

    async def extract(
        self, content: str, reference_time: datetime, ontology: Optional[dict] = None
    ) -> ExtractionResult:
        from graphiti_core.nodes import EpisodeType as GEpisodeType  # noqa

        results = await self._graphiti.add_episode(
            name=f"episode-{reference_time.isoformat()}",
            episode_body=content,
            source_description="claw-zep ingest",
            reference_time=reference_time,
            group_id=self._group_id,
        )

        out = ExtractionResult(extractor=self.name)
        uuid_map: dict[str, ExtractedEntity] = {}
        for node in results.nodes:
            ent = ExtractedEntity(
                name=node.name,
                entity_type=(node.labels[0] if getattr(node, "labels", None) else "Entity"),
                summary=getattr(node, "summary", None),
                uuid=node.uuid,
                attributes=getattr(node, "attributes", {}) or {},
            )
            uuid_map[node.uuid] = ent
            out.entities.append(ent)

        for edge in results.edges:
            out.relations.append(
                ExtractedRelation(
                    source_uuid=edge.source_node_uuid,
                    target_uuid=edge.target_node_uuid,
                    relation_type=edge.name,
                    fact=edge.fact,
                    source_name=uuid_map.get(edge.source_node_uuid, ExtractedEntity("")).name or None,
                    target_name=uuid_map.get(edge.target_node_uuid, ExtractedEntity("")).name or None,
                    uuid=edge.uuid,
                    valid_at=getattr(edge, "valid_at", None) or reference_time,
                    invalid_at=getattr(edge, "invalid_at", None),
                )
            )
        return out
