"""
Webhook 模型
=============
项目级回调配置，订阅记忆/图谱/记忆树变更事件。
对标 Zep 的 Webhook 机制。变更发生时由 Celery 异步投递，
WebhookDelivery 记录每次投递结果以支持重试与审计。
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import UUIDBase


class WebhookEventType(str, Enum):
    """可订阅的事件类型"""
    EPISODE_INGESTED = "episode.ingested"
    EPISODE_PROCESSED = "episode.processed"
    ENTITY_CREATED = "entity.created"
    ENTITY_UPDATED = "entity.updated"
    ENTITY_EXPIRED = "entity.expired"
    RELATION_CREATED = "relation.created"
    RELATION_EXPIRED = "relation.expired"
    MEMORY_TREE_NODE_CREATED = "memory_tree.node_created"
    MEMORY_TREE_NODE_UPDATED = "memory_tree.node_updated"
    TEMPORAL_CONFLICT_RESOLVED = "temporal.conflict_resolved"


class Webhook(UUIDBase):
    __tablename__ = "webhooks"
    __table_args__ = (
        Index("ix_webhooks_project_id", "project_id"),
        Index("ix_webhooks_tenant_id", "tenant_id"),
        Index("ix_webhooks_is_active", "is_active"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False, comment="回调地址")
    # 订阅事件列表，JSON 数组，存 WebhookEventType 值；["*"] 表示全部
    events_json: Mapped[str] = mapped_column(Text, nullable=False, default='["*"]')
    # HMAC 签名密钥（明文存储，仅用于服务端对 payload 签名；建议加密）
    secret: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 投递统计
    total_deliveries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_deliveries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    deliveries: Mapped[List["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="webhook", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Webhook id={self.id} url={self.target_url} active={self.is_active}>"


class WebhookDelivery(UUIDBase):
    """单次 Webhook 投递记录"""
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_webhook_id", "webhook_id"),
        Index("ix_webhook_deliveries_status", "status"),
        Index("ix_webhook_deliveries_created_at", "created_at"),
    )

    webhook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
        comment="pending|success|failed",
    )
    http_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    webhook: Mapped["Webhook"] = relationship("Webhook", back_populates="deliveries")
