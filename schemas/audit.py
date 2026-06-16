"""审计日志 schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import ORMModel


class AuditLogFilter(BaseModel):
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    user_id: Optional[str] = None
    result: Optional[str] = Field(default=None, description="success|failure")
    created_at_gte: Optional[datetime] = None
    created_at_lte: Optional[datetime] = None


class AuditLogOut(ORMModel):
    id: str
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    result: str
    error_message: Optional[str] = None
    created_at: datetime
