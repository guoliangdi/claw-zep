"""
RBAC 权限模型
===============
Role → Permission 多对多，User → Role 多对多（项目级别绑定）。

权限编码规范：<resource>:<action>
  例：project:read  graph:write  memory_tree:delete  tenant:manage
"""
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, ForeignKey, String, Text,
    UniqueConstraint, Index, Table, Column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.base import UUIDBase

if TYPE_CHECKING:
    from models.user import User


# 角色-权限关联表（多对多）
role_permission_table = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(UUIDBase):
    """细粒度权限点"""
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_permissions_code"),
    )

    code: Mapped[str] = mapped_column(String(128), nullable=False, comment="权限编码，如 graph:write")
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resource: Mapped[str] = mapped_column(String(64), nullable=False, comment="资源类型")
    action: Mapped[str] = mapped_column(String(32), nullable=False, comment="操作类型")

    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=role_permission_table, back_populates="permissions", lazy="noload"
    )


class Role(UUIDBase):
    """角色：系统内置角色 + 租户自定义角色"""
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", "tenant_id", name="uq_roles_name_tenant"),
        Index("ix_roles_tenant_id", "tenant_id"),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="系统内置角色不可删除")
    # NULL = 全局角色（super_admin/tenant_admin），否则为租户范围角色
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )

    permissions: Mapped[List["Permission"]] = relationship(
        "Permission", secondary=role_permission_table, back_populates="roles", lazy="noload"
    )
    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="role", lazy="noload")


class UserRole(UUIDBase):
    """用户-角色绑定（支持项目级别隔离）"""
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "project_id", name="uq_user_roles"),
        Index("ix_user_roles_user_id", "user_id"),
        Index("ix_user_roles_project_id", "project_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = 租户级别角色绑定，非空 = 项目级别角色绑定
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="user_roles")
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")


# ---- 系统内置权限常量 ----
SYSTEM_PERMISSIONS = [
    # 租户管理
    ("tenant:read",    "查看租户",    "tenant", "read"),
    ("tenant:manage",  "管理租户",    "tenant", "manage"),
    # 项目
    ("project:read",   "查看项目",    "project", "read"),
    ("project:write",  "创建/编辑项目", "project", "write"),
    ("project:delete", "删除项目",    "project", "delete"),
    # 图谱
    ("graph:read",     "查看图谱",    "graph", "read"),
    ("graph:write",    "写入图谱",    "graph", "write"),
    ("graph:delete",   "删除图谱数据", "graph", "delete"),
    # 记忆
    ("memory:read",    "读取记忆",    "memory", "read"),
    ("memory:write",   "写入记忆",    "memory", "write"),
    ("memory:delete",  "删除记忆",    "memory", "delete"),
    # 记忆树
    ("memory_tree:read",   "查看记忆树",   "memory_tree", "read"),
    ("memory_tree:write",  "编辑记忆树",   "memory_tree", "write"),
    ("memory_tree:delete", "删除记忆树节点", "memory_tree", "delete"),
    # 时序
    ("temporal:read",  "查看时序快照", "temporal", "read"),
    # 用户管理
    ("user:read",      "查看用户",    "user", "read"),
    ("user:manage",    "管理用户",    "user", "manage"),
    # 审计
    ("audit:read",     "查看审计日志", "audit", "read"),
    # Webhook
    ("webhook:manage", "管理Webhook", "webhook", "manage"),
    # OpenClaw 接入
    ("openclaw:access", "OpenClaw记忆接入", "openclaw", "access"),
]

SYSTEM_ROLES = {
    "super_admin": [p[0] for p in SYSTEM_PERMISSIONS],
    "tenant_admin": [
        "project:read", "project:write", "project:delete",
        "graph:read", "graph:write", "graph:delete",
        "memory:read", "memory:write", "memory:delete",
        "memory_tree:read", "memory_tree:write", "memory_tree:delete",
        "temporal:read",
        "user:read", "user:manage",
        "audit:read",
        "webhook:manage",
        "openclaw:access",
    ],
    "project_owner": [
        "project:read", "project:write",
        "graph:read", "graph:write", "graph:delete",
        "memory:read", "memory:write", "memory:delete",
        "memory_tree:read", "memory_tree:write", "memory_tree:delete",
        "temporal:read",
        "user:read",
        "audit:read",
        "webhook:manage",
        "openclaw:access",
    ],
    "project_editor": [
        "project:read",
        "graph:read", "graph:write",
        "memory:read", "memory:write",
        "memory_tree:read", "memory_tree:write",
        "temporal:read",
        "openclaw:access",
    ],
    "project_viewer": [
        "project:read",
        "graph:read",
        "memory:read",
        "memory_tree:read",
        "temporal:read",
    ],
}
