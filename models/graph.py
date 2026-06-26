"""
图谱数据模型（PostgreSQL 元数据层）
=====================================
Kuzu 存储实际图数据（实体节点+关系边），PostgreSQL 存储：
  1. Episode 会话记录（原始输入 + 处理状态 + 时序标注）
  2. 图谱元数据索引（用于跨库检索路由、审计追踪）

TemporalMixin 强制挂载双时序字段。
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import UUIDBase
from models.temporal_mixin import TemporalMixin


class EpisodeStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EpisodeType(str, Enum):
    MESSAGE = "message"
    TEXT = "text"
    JSON = "json"
    FACT_TRIPLE = "fact_triple"


class Episode(UUIDBase, TemporalMixin):
    """
    会话/输入记录（对标 Graphiti EpisodeNode）
    每条 Episode 经 graphiti_orchestrator 处理后，抽取实体+关系写入 Kuzu。
    """
    __tablename__ = "episodes"
    __table_args__ = (
        Index("ix_episodes_project_id", "project_id"),
        Index("ix_episodes_tenant_id", "tenant_id"),
        Index("ix_episodes_status", "status"),
        Index("ix_episodes_episode_type", "episode_type"),
        Index("ix_episodes_valid_from", "valid_from"),
        Index("ix_episodes_group_id", "group_id"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # Graphiti 原生字段
    graphiti_uuid: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, unique=True, comment="对应 Graphiti 中 EpisodeNode.uuid"
    )
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="原始输入内容")
    episode_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EpisodeType.TEXT
    )
    # message 类型需要 source_description（如 "user: xxx"）
    source_description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # 处理状态
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EpisodeStatus.PENDING
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 处理结果统计
    extracted_entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extracted_relation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 分组（同一对话 session 共享 group_id）
    group_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class GraphEntityMeta(UUIDBase, TemporalMixin):
    """
    图谱实体元数据（Kuzu 实体的 PostgreSQL 镜像索引）
    用于跨库全文检索、时序快照、审计追踪。
    Kuzu 存储完整图数据，此处存储关键字段供 SQL 查询。
    """
    __tablename__ = "graph_entity_meta"
    __table_args__ = (
        Index("ix_graph_entity_meta_project_id", "project_id"),
        Index("ix_graph_entity_meta_tenant_id", "tenant_id"),
        Index("ix_graph_entity_meta_entity_type", "entity_type"),
        Index("ix_graph_entity_meta_kuzu_uuid", "kuzu_uuid"),
        Index("ix_graph_entity_meta_valid_from", "valid_from"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # Graphiti/Kuzu 对应标识
    kuzu_uuid: Mapped[str] = mapped_column(String(36), nullable=False, comment="Kuzu 中 EntityNode.uuid")
    graphiti_uuid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="本体定义中的实体类型")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 扩展属性（如舆情 risk_level/signal 等），JSON 字符串
    attributes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Chroma 向量索引 ID
    chroma_doc_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # 关联 Episode
    source_episode_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class GraphRelationMeta(UUIDBase, TemporalMixin):
    """
    图谱关系元数据（Kuzu 边的 PostgreSQL 镜像索引）
    """
    __tablename__ = "graph_relation_meta"
    __table_args__ = (
        Index("ix_graph_relation_meta_project_id", "project_id"),
        Index("ix_graph_relation_meta_tenant_id", "tenant_id"),
        Index("ix_graph_relation_meta_source_entity", "source_entity_kuzu_uuid"),
        Index("ix_graph_relation_meta_target_entity", "target_entity_kuzu_uuid"),
        Index("ix_graph_relation_meta_valid_from", "valid_from"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # 关系逻辑键存「source|type|target」组合，需足够长度（实体 kuzu_uuid 仍为 36）
    kuzu_uuid: Mapped[str] = mapped_column(String(512), nullable=False)
    graphiti_uuid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    relation_type: Mapped[str] = mapped_column(String(128), nullable=False)
    fact: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="关系事实描述")

    source_entity_kuzu_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    target_entity_kuzu_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    source_entity_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    target_entity_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # 因果权重（Palantir 推演使用）
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    source_episode_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
