"""
claw-zep ORM 模型聚合导出
==========================
统一在此导入全部模型，确保：
  1. SQLAlchemy metadata 完整（Alembic 自动生成迁移、init_db 建表）
  2. 业务层可 `from models import Tenant, User, ...` 直接引用
"""
from models.base import UUIDBase, utcnow
from models.temporal_mixin import TemporalMixin
from models.tenant import Tenant, TenantStatus
from models.user import User, SystemRole, UserStatus
from models.rbac import (
    Permission,
    Role,
    UserRole,
    role_permission_table,
    SYSTEM_PERMISSIONS,
    SYSTEM_ROLES,
)
from models.project import (
    Project,
    ProjectStatus,
    ProjectAPIKey,
    ProjectMember,
)
from models.graph import (
    Episode,
    EpisodeStatus,
    EpisodeType,
    GraphEntityMeta,
    GraphRelationMeta,
)
from models.memory_tree import (
    MemoryTreeNode,
    MemoryTreeNodeVersion,
    TreeLayer,
    NodeStatus,
)
from models.ontology import Ontology
from models.webhook import Webhook, WebhookDelivery, WebhookEventType
from models.audit import AuditLog, AuditAction

__all__ = [
    # base
    "UUIDBase",
    "TemporalMixin",
    "utcnow",
    # tenant
    "Tenant",
    "TenantStatus",
    # user
    "User",
    "SystemRole",
    "UserStatus",
    # rbac
    "Permission",
    "Role",
    "UserRole",
    "role_permission_table",
    "SYSTEM_PERMISSIONS",
    "SYSTEM_ROLES",
    # project
    "Project",
    "ProjectStatus",
    "ProjectAPIKey",
    "ProjectMember",
    # graph
    "Episode",
    "EpisodeStatus",
    "EpisodeType",
    "GraphEntityMeta",
    "GraphRelationMeta",
    # memory tree
    "MemoryTreeNode",
    "MemoryTreeNodeVersion",
    "TreeLayer",
    "NodeStatus",
    # ontology
    "Ontology",
    # webhook
    "Webhook",
    "WebhookDelivery",
    "WebhookEventType",
    # audit
    "AuditLog",
    "AuditAction",
]
