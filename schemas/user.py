"""用户与项目成员 schema。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from schemas.common import ORMModel


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: Optional[str] = None
    system_role: str = Field(default="member", description="super_admin|tenant_admin|member")
    tenant_id: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, max_length=64)
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    status: Optional[str] = Field(default=None, description="active|inactive|locked")
    system_role: Optional[str] = None


class UserOut(ORMModel):
    id: str
    email: str
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    system_role: str
    status: str
    tenant_id: Optional[str] = None
    last_login_at: Optional[datetime] = None
    api_key_prefix: Optional[str] = None
    created_at: datetime


class ProjectMemberCreate(BaseModel):
    user_id: str
    project_role: str = Field(
        default="project_viewer",
        description="project_owner|project_editor|project_viewer",
    )


class ProjectMemberUpdate(BaseModel):
    project_role: str


class ProjectMemberOut(ORMModel):
    id: str
    project_id: str
    user_id: str
    project_role: str
    invited_by: Optional[str] = None
    created_at: datetime
    # 关联用户信息（可选填充）
    user: Optional[UserOut] = None


class APIKeyCreateResponse(BaseModel):
    """创建用户/项目 API Key 时一次性返回明文。"""
    id: str
    name: Optional[str] = None
    api_key: str = Field(description="明文密钥，仅创建时返回一次")
    key_prefix: str
