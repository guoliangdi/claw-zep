"""
Ontology 本体模型
==================
项目级本体定义，描述允许的实体类型、关系类型及其属性 schema。
对标 Zep 的 Ontology / Graphiti 的 entity_types / edge_types 机制：
  - graphiti_orchestrator 抽取时将本体作为 LLM 约束传入
  - 前端「项目本体查看编辑」页面读写此表

本体本身随业务演进，挂载 TemporalMixin 支持版本化（一个 project 同一时刻
只有一条 valid_until IS NULL 的「当前生效」本体，历史版本保留以供回溯）。
"""
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import UUIDBase
from models.temporal_mixin import TemporalMixin


class Ontology(UUIDBase, TemporalMixin):
    __tablename__ = "ontologies"
    __table_args__ = (
        Index("ix_ontologies_project_id", "project_id"),
        Index("ix_ontologies_tenant_id", "tenant_id"),
        Index("ix_ontologies_valid_until", "valid_until"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 实体类型定义，JSON 数组：
    # [{"name":"Person","description":"...","properties":[{"name":"role","type":"str"}]}]
    entity_types_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 关系（边）类型定义，JSON 数组：
    # [{"name":"WORKS_FOR","source":"Person","target":"Organization","description":"..."}]
    edge_types_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 是否为当前生效版本（冗余字段，便于快速查询当前本体）
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="当前生效标记"
    )

    def __repr__(self) -> str:
        return f"<Ontology id={self.id} project={self.project_id} v{self.version}>"
