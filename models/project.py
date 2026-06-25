"""
Project 项目模型
==================
租户下的逻辑隔离单元，全量数据（图谱/记忆/记忆树）均绑定 project_id。
对标 Zep 原生 Project，扩展了 Ontology 配置、LLM 覆盖配置、API Key 管理。
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import UUIDBase

if TYPE_CHECKING:
    from models.tenant import Tenant
    from models.user import User
    from models.rbac import UserRole


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Project(UUIDBase):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("slug", "tenant_id", name="uq_projects_slug_tenant"),
        Index("ix_projects_tenant_id", "tenant_id"),
        Index("ix_projects_status", "status"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, comment="项目标识符")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ProjectStatus.ACTIVE)

    # LLM 配置覆盖（不填则继承全局 settings）
    llm_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    llm_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 图谱配置
    kuzu_graph_name: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="对应 Kuzu 中的 graph 命名空间"
    )
    chroma_collection_name: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="对应 Chroma 中的 collection"
    )

    # Ontology JSON（项目级别本体定义，扩展全局本体）
    ontology_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="实体/关系类型定义，JSON格式"
    )

    # 融合组：同租户内同 fusion_group 的项目允许跨项目联合检索/推演（NULL=不参与融合）
    fusion_group: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="知识域/融合组标识，隔离=默认，融合=显式开关"
    )

    # 统计缓存（定时更新，避免实时 count 查询）
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    episode_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memory_tree_node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 关联
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="projects")
    api_keys: Mapped[List["ProjectAPIKey"]] = relationship(
        "ProjectAPIKey", back_populates="project", lazy="noload"
    )
    members: Mapped[List["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="project", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} slug={self.slug} tenant={self.tenant_id}>"


class ProjectAPIKey(UUIDBase):
    """项目级 API Key，用于 OpenClaw / 龙虾 SDK 鉴权"""
    __tablename__ = "project_api_keys"
    __table_args__ = (
        Index("ix_project_api_keys_project_id", "project_id"),
        Index("ix_project_api_keys_key_hash", "key_hash"),
    )

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="Key 名称/备注")
    key_hash: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, comment="明文前缀供展示，如 yz_live_xxxx")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="api_keys")


class ProjectMember(UUIDBase):
    """项目成员，绑定用户 + 项目角色"""
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members"),
        Index("ix_project_members_user_id", "user_id"),
    )

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="project_viewer",
        comment="project_owner | project_editor | project_viewer"
    )
    invited_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="project_members")
