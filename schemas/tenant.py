"""租户 schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import ORMModel


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: Optional[str] = None
    contact_email: Optional[str] = None
    max_projects: int = Field(default=10, ge=1)
    max_users: int = Field(default=50, ge=1)
    max_memory_mb: int = Field(default=1024, ge=1)
    max_api_calls_per_day: int = Field(default=10000, ge=0)
    # 初始管理员
    admin_email: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[str] = Field(default=None, min_length=8)


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[str] = Field(default=None, description="active|suspended|pending")
    max_projects: Optional[int] = Field(default=None, ge=1)
    max_users: Optional[int] = Field(default=None, ge=1)
    max_memory_mb: Optional[int] = Field(default=None, ge=1)
    max_api_calls_per_day: Optional[int] = Field(default=None, ge=0)


class TenantOut(ORMModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    max_projects: int
    max_users: int
    max_memory_mb: int
    max_api_calls_per_day: int
    contact_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
