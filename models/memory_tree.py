"""
OpenHuman MemoryTree 记忆树节点模型
======================================
三层架构：
  SourceTree  → 原始数据源树（Episode 粒度，自动构建）
  TopicTree   → 主题聚合树（LLM 归纳，每棵树一个主题）
  GlobalTree  → 全局周期摘要树（跨主题、跨时间段摘要）

全部节点：
  - Markdown 正文存 PostgreSQL（≤64KB），超大内容存对象存储
  - 挂载 TemporalMixin 双时序字段
  - 支持父子关系（self-referential）
  - 支持与图谱实体关联（entity_refs JSON）
  - 支持 Obsidian 格式导出（[[wikilink]]）
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import UUIDBase
from models.temporal_mixin import TemporalMixin


class TreeLayer(str, Enum):
    SOURCE = "source"    # 数据源原始树
    TOPIC = "topic"      # 主题聚合树
    GLOBAL = "global"    # 全局周期摘要树


class NodeStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"


class MemoryTreeNode(UUIDBase, TemporalMixin):
    """
    记忆树节点（三层通用，通过 tree_layer 区分）
    """
    __tablename__ = "memory_tree_nodes"
    __table_args__ = (
        Index("ix_mtn_project_id", "project_id"),
        Index("ix_mtn_tenant_id", "tenant_id"),
        Index("ix_mtn_tree_layer", "tree_layer"),
        Index("ix_mtn_parent_id", "parent_id"),
        Index("ix_mtn_topic_id", "topic_id"),
        Index("ix_mtn_valid_from", "valid_from"),
        Index("ix_mtn_status", "status"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    tree_layer: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="source|topic|global"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=NodeStatus.ACTIVE)

    # 树形结构
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("memory_tree_nodes.id", ondelete="SET NULL"), nullable=True
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="树深度，根节点=0")
    path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True, comment="物化路径，如 /root_id/child_id/..."
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="同级排序")

    # 内容
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    # Markdown 正文，≤64KB 存此字段；超大内容存对象存储后此字段存 object_key
    content_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_object_key: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, comment="对象存储 Key，内容超大时使用"
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="LLM生成的节点摘要")

    # 主题标签（TopicTree 主题 ID / 会话 group_id / OpenClaw 文档键 openclaw:<key>）
    topic_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    topic_label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # 关联图谱实体（JSON 数组，存 kuzu_uuid 列表）
    entity_refs_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment='关联实体 kuzu_uuid 列表，JSON数组格式'
    )

    # 关联 Episode
    source_episode_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Chroma 向量索引
    chroma_doc_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # GlobalTree 专用：周期范围
    period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="GlobalTree 摘要覆盖的起始时间"
    )
    period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="GlobalTree 摘要覆盖的结束时间"
    )

    # 统计
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    child_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 自关联
    children: Mapped[List["MemoryTreeNode"]] = relationship(
        "MemoryTreeNode",
        foreign_keys=[parent_id],
        back_populates="parent",
        lazy="noload",
    )
    parent: Mapped[Optional["MemoryTreeNode"]] = relationship(
        "MemoryTreeNode",
        foreign_keys=[parent_id],
        back_populates="children",
        remote_side="MemoryTreeNode.id",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<MemoryTreeNode id={self.id} layer={self.tree_layer} title={self.title[:30]}>"


class MemoryTreeNodeVersion(UUIDBase):
    """
    节点版本历史（每次编辑前快照）
    支持回溯到任意历史版本。
    """
    __tablename__ = "memory_tree_node_versions"
    __table_args__ = (
        Index("ix_mtnv_node_id", "node_id"),
        Index("ix_mtnv_project_id", "project_id"),
    )

    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_tree_nodes.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_object_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    changed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, comment="操作用户ID")
    change_summary: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
