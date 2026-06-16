"""
多租户模型
===========
三级租户架构：
  SuperAdmin（系统内置）→ Tenant（租户/组织）→ TenantMember（租户成员）

Tenant 对标 Zep 的 Organization 概念，额外增加配额管理。
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import UUIDBase

if TYPE_CHECKING:
    from models.project import Project
    from models.user import User


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class Tenant(UUIDBase):
    """租户/组织"""
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        Index("ix_tenants_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="租户名称")
    slug: Mapped[str] = mapped_column(String(64), nullable=False, comment="URL友好标识")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TenantStatus.ACTIVE
    )

    # 配额限制
    max_projects: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    max_api_calls_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)

    # 元数据
    contact_email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="扩展JSON配置")

    # 关联
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="tenant", lazy="noload")
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="tenant", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} slug={self.slug} status={self.status}>"
