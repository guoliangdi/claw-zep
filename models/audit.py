"""
审计日志模型
=============
全链路操作记录，支持合规审计。
不继承 TemporalMixin（审计日志本身不可变，不需要时序管理）。
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import UUIDBase


class AuditAction(str, Enum):
    # 认证
    LOGIN = "auth.login"
    LOGOUT = "auth.logout"
    LOGIN_FAILED = "auth.login_failed"
    # 租户
    TENANT_CREATE = "tenant.create"
    TENANT_UPDATE = "tenant.update"
    TENANT_SUSPEND = "tenant.suspend"
    # 项目
    PROJECT_CREATE = "project.create"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    # 图谱
    EPISODE_INGEST = "graph.episode_ingest"
    ENTITY_DELETE = "graph.entity_delete"
    RELATION_DELETE = "graph.relation_delete"
    # 记忆树
    MEMORY_TREE_CREATE = "memory_tree.create"
    MEMORY_TREE_UPDATE = "memory_tree.update"
    MEMORY_TREE_DELETE = "memory_tree.delete"
    MEMORY_TREE_EXPORT = "memory_tree.export"
    # 用户
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    ROLE_ASSIGN = "user.role_assign"
    # API Key
    API_KEY_CREATE = "api_key.create"
    API_KEY_REVOKE = "api_key.revoke"
    # Webhook
    WEBHOOK_CREATE = "webhook.create"
    WEBHOOK_DELETE = "webhook.delete"


class AuditLog(UUIDBase):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_project_id", "project_id"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_resource_type", "resource_type"),
    )

    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="冗余存储，避免用户删除后日志丢失关联")

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # 变更快照
    before_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="变更前数据快照")
    after_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="变更后数据快照")
    extra_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="附加上下文")

    # 请求上下文
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    result: Mapped[str] = mapped_column(String(16), nullable=False, default="success", comment="success|failure")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
