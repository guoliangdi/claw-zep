"""认证相关 schema：登录、令牌、当前用户上下文。"""
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    tenant_slug: Optional[str] = Field(
        default=None, description="可选：指定登录租户（多租户场景）"
    )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="access_token 有效期（秒）")


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class CurrentUser(ORMModel):
    """鉴权中间件注入的当前用户上下文。"""
    id: str
    email: str
    username: str
    display_name: Optional[str] = None
    system_role: str
    tenant_id: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)

    @property
    def is_super_admin(self) -> bool:
        return self.system_role == "super_admin"


class TokenPayload(BaseModel):
    """JWT 载荷结构。"""
    sub: str            # user id
    email: str
    system_role: str
    tenant_id: Optional[str] = None
    type: str = "access"  # access | refresh
    exp: Optional[int] = None
