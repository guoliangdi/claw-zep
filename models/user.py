"""
用户模型
=========
系统内用户分两个维度：
  1. 系统角色：super_admin | tenant_admin | member
  2. 项目角色：通过 ProjectMember 绑定（owner / editor / viewer）

User 绑定到某个 Tenant，super_admin 用户 tenant_id 可为空。
"""
from datetime import datetime, timezone
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
    from models.project import ProjectMember
    from models.rbac import UserRole


class SystemRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    MEMBER = "member"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"


class User(UUIDBase):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_system_role", "system_role"),
    )

    email: Mapped[str] = mapped_column(String(256), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    system_role: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SystemRole.MEMBER
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=UserStatus.ACTIVE
    )

    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )

    # 安全字段
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # API Key（用于 OpenClaw 等客户端直接鉴权）
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, unique=True)
    api_key_prefix: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="明文前缀供展示")

    # 关联
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="users")
    project_members: Mapped[List["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="user", lazy="noload"
    )
    user_roles: Mapped[List["UserRole"]] = relationship(
        "UserRole", back_populates="user", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.system_role}>"
