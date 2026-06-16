"""RBAC schema：权限、角色、用户角色绑定。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.common import ORMModel


class PermissionOut(ORMModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    resource: str
    action: str


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = None
    permission_codes: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    permission_codes: Optional[List[str]] = None


class RoleOut(ORMModel):
    id: str
    name: str
    description: Optional[str] = None
    is_system: bool
    tenant_id: Optional[str] = None
    permissions: List[PermissionOut] = Field(default_factory=list)
    created_at: datetime


class UserRoleAssign(BaseModel):
    user_id: str
    role_id: str
    project_id: Optional[str] = Field(
        default=None, description="为空=租户级绑定，非空=项目级绑定"
    )


class UserRoleOut(ORMModel):
    id: str
    user_id: str
    role_id: str
    project_id: Optional[str] = None
    created_at: datetime
