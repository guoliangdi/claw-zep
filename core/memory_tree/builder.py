"""
三层记忆树构建
==============
  SourceTree  —— 每条 Episode 自动生成一个源节点（orchestrator 钩子调用）
  TopicTree   —— 将源节点按主题聚合（按共享实体/标签启发式聚类）
  GlobalTree  —— 按周期对主题/源节点做全局摘要

全部节点经 MemoryTreeService 落库，绑定 valid_from 与关联实体。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory_tree.service import MemoryTreeService, _loads_refs
from core.memory_tree.summarizer import generate_summary, synthesize_topic_summary
from models.memory_tree import MemoryTreeNode, TreeLayer

logger = structlog.get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryTreeBuilder:
    # ---------------- SourceTree ----------------
    @staticmethod
    async def build_source_node(db: AsyncSession, episode: Any, result: Any) -> MemoryTreeNode:
        """
        orchestrator 钩子：为一条 Episode 生成 SourceTree 节点。
        result 为 ExtractionResult（含 entities/relations）。
        """
        entity_refs = [getattr(e, "uuid", None) for e in getattr(result, "entities", [])]
        entity_refs = [r for r in entity_refs if r]
        title = episode.name or (episode.content[:40] + ("…" if len(episode.content) > 40 else ""))
        summary = await generate_summary(episode.content, max_chars=160)

        # 同一会话（group_id）作为父源节点聚合
        parent_id = None
        if episode.group_id:
            from sqlalchemy import select

            parent = await db.scalar(
                select(MemoryTreeNode).where(
                    MemoryTreeNode.project_id == episode.project_id,
                    MemoryTreeNode.tree_layer == TreeLayer.SOURCE.value,
                    MemoryTreeNode.topic_id == episode.group_id,
                    MemoryTreeNode.parent_id.is_(None),
                )
            )
            if parent is None:
                parent = await MemoryTreeService.create_node(
                    db, episode.tenant_id, episode.project_id,
                    tree_layer=TreeLayer.SOURCE.value,
                    title=f"会话 {episode.group_id[:8]}",
                    topic_id=episode.group_id,
                    valid_from=episode.valid_from,
                )
            parent_id = parent.id

        node = await MemoryTreeService.create_node(
            db, episode.tenant_id, episode.project_id,
            tree_layer=TreeLayer.SOURCE.value,
            title=title,
            content_markdown=episode.content,
            parent_id=parent_id,
            topic_id=episode.group_id,
            entity_refs=entity_refs,
            source_episode_id=episode.id,
            summary=summary,
            valid_from=episode.valid_from,
        )
        return node

    # ---------------- TopicTree ----------------
    @classmethod
    async def build_topic_tree(
        cls, db: AsyncSession, tenant_id: str, project_id: str
    ) -> List[MemoryTreeNode]:
        """按共享实体启发式聚类源节点 → 生成/更新主题节点。"""
        sources = await MemoryTreeService.list_nodes(
            db, project_id, tree_layer=TreeLayer.SOURCE.value
        )
        # 以『首个关联实体』作为主题键（简单聚类；LLM 可后续增强）
        clusters: dict[str, List[MemoryTreeNode]] = defaultdict(list)
        for s in sources:
            refs = _loads_refs(s.entity_refs_json)
            key = refs[0] if refs else (s.topic_id or "未归类")
            clusters[key].append(s)

        topic_nodes: List[MemoryTreeNode] = []
        for topic_key, members in clusters.items():
            if len(members) < 1:
                continue
            label = members[0].title[:24]
            summaries = [m.summary or m.title for m in members]
            topic_summary = await synthesize_topic_summary(summaries, label)
            all_refs: List[str] = []
            for m in members:
                all_refs.extend(_loads_refs(m.entity_refs_json))
            topic_node = await MemoryTreeService.create_node(
                db, tenant_id, project_id,
                tree_layer=TreeLayer.TOPIC.value,
                title=f"主题：{label}",
                content_markdown=topic_summary,
                summary=topic_summary,
                topic_id=topic_key,
                topic_label=label,
                entity_refs=list(dict.fromkeys(all_refs)),
            )
            topic_nodes.append(topic_node)
        logger.info("topic tree built", project_id=project_id, topics=len(topic_nodes))
        return topic_nodes

    # ---------------- GlobalTree ----------------
    @classmethod
    async def build_global_summary(
        cls,
        db: AsyncSession,
        tenant_id: str,
        project_id: str,
        period_hours: int = 24,
    ) -> Optional[MemoryTreeNode]:
        """对最近 period_hours 的主题/源节点做全局周期摘要。"""
        period_end = utcnow()
        period_start = period_end - timedelta(hours=period_hours)

        topics = await MemoryTreeService.list_nodes(
            db, project_id, tree_layer=TreeLayer.TOPIC.value
        )
        recent = [t for t in topics if t.created_at and t.created_at >= period_start]
        basis = recent or topics
        if not basis:
            return None

        summaries = [t.summary or t.title for t in basis]
        global_summary = await synthesize_topic_summary(
            summaries, topic=f"{period_start.date()} ~ {period_end.date()} 全局"
        )
        node = await MemoryTreeService.create_node(
            db, tenant_id, project_id,
            tree_layer=TreeLayer.GLOBAL.value,
            title=f"全局摘要 {period_end.date()}",
            content_markdown=global_summary,
            summary=global_summary,
            period_start=period_start,
            period_end=period_end,
        )
        logger.info("global summary built", project_id=project_id, basis=len(basis))
        return node


memory_tree_builder = MemoryTreeBuilder()
