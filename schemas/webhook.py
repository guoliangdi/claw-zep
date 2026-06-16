"""Webhook schema。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl

from schemas.common import ORMModel


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    target_url: str = Field(description="回调地址")
    events: List[str] = Field(
        default_factory=lambda: ["*"],
        description='订阅事件，["*"]=全部',
    )
    secret: Optional[str] = Field(default=None, description="HMAC 签名密钥")
    is_active: bool = True


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    target_url: Optional[str] = None
    events: Optional[List[str]] = None
    secret: Optional[str] = None
    is_active: Optional[bool] = None


class WebhookOut(ORMModel):
    id: str
    project_id: str
    name: str
    target_url: str
    events: List[str] = Field(default_factory=list)
    is_active: bool
    total_deliveries: int
    failed_deliveries: int
    last_triggered_at: Optional[datetime] = None
    created_at: datetime


class WebhookDeliveryOut(ORMModel):
    id: str
    webhook_id: str
    event_type: str
    status: str
    http_status_code: Optional[int] = None
    attempt_count: int
    error_message: Optional[str] = None
    created_at: datetime
