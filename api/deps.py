"""
FastAPI 依赖
=============
认证、多租户解析、项目上下文校验、RBAC 权限校验，统一在此提供。

调用约定（前端全局拦截器自动携带）：
  Authorization: Bearer <JWT>     —— 身份
  X-Tenant-ID:   <tenant_id>      —— 租户（普通用户被锁定为自身租户）
  X-Project-ID:  <project_id>     —— 当前项目（数据隔离维度）
"""
from dataclasses import dataclass
from typing import Optional, Sequence, Set

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import context as ctx
from core.database import get_db
from core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from core.permissions import has_permission, resolve_permissions
from core.security import decode_token, hash_api_key
from datetime import datetime, timezone

from models.project import Project, ProjectAPIKey
from models.user import SystemRole, User, UserStatus
from schemas.auth import CurrentUser

bearer_scheme = HTTPBearer(auto_error=False)


# ---------------- 认证 ----------------
async def _load_user_by_jwt(token: str, db: AsyncSession) -> User:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedError("令牌类型错误，需要 access token")
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("令牌缺少 subject")
    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("用户不存在")
    return user


async def _load_user_by_api_key(api_key: str, db: AsyncSession) -> User:
    key_hash = hash_api_key(api_key)
    user = await db.scalar(select(User).where(User.api_key_hash == key_hash))
    if user is None:
        raise UnauthorizedError("无效的 API Key")
    return user


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """解析当前用户（JWT 优先，其次用户级 API Key），并解析其权限集合。"""
    user: Optional[User] = None
    if credentials and credentials.scheme.lower() == "bearer":
        user = await _load_user_by_jwt(credentials.credentials, db)
    elif x_api_key:
        user = await _load_user_by_api_key(x_api_key, db)

    if user is None:
        raise UnauthorizedError("未认证：缺少 Authorization 或 X-API-Key")
    if user.status != UserStatus.ACTIVE.value:
        raise ForbiddenError("用户已被禁用或锁定")

    # 以请求头中的项目作为权限解析范围
    project_id = request.headers.get("X-Project-ID")
    perms: Set[str] = await resolve_permissions(db, user, project_id)

    ctx.set_user_id(user.id)

    return CurrentUser(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        system_role=user.system_role,
        tenant_id=user.tenant_id,
        permissions=sorted(perms),
    )


# ---------------- 多租户解析 ----------------
async def get_effective_tenant_id(
    current_user: CurrentUser = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    """
    解析当前请求作用的租户：
      - 超级管理员：可通过 X-Tenant-ID 指定任意租户
      - 普通用户：强制锁定为自身 tenant_id，忽略/校验 X-Tenant-ID
    """
    if current_user.is_super_admin:
        tenant_id = x_tenant_id or current_user.tenant_id
        if not tenant_id:
            raise ForbiddenError("超级管理员需通过 X-Tenant-ID 指定目标租户")
        ctx.set_tenant_id(tenant_id)
        return tenant_id

    if not current_user.tenant_id:
        raise ForbiddenError("用户未绑定租户")
    if x_tenant_id and x_tenant_id != current_user.tenant_id:
        raise ForbiddenError("无权访问其他租户数据")
    ctx.set_tenant_id(current_user.tenant_id)
    return current_user.tenant_id


# ---------------- 项目上下文 ----------------
@dataclass
class ProjectContext:
    project: Project
    tenant_id: str
    user: CurrentUser

    @property
    def project_id(self) -> str:
        return self.project.id


async def get_project_context(
    x_project_id: Optional[str] = Header(default=None, alias="X-Project-ID"),
    tenant_id: str = Depends(get_effective_tenant_id),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectContext:
    """校验 X-Project-ID 属于当前租户，并写入隔离上下文。"""
    if not x_project_id:
        raise ForbiddenError("缺少 X-Project-ID 请求头")
    project = await db.get(Project, x_project_id)
    if project is None:
        raise NotFoundError("项目不存在", detail=x_project_id)
    if project.tenant_id != tenant_id:
        raise ForbiddenError("项目不属于当前租户")

    ctx.set_project_id(project.id)
    return ProjectContext(project=project, tenant_id=tenant_id, user=current_user)


# ---------------- RBAC 权限校验 ----------------
def require_permissions(*codes: str, require_all: bool = True):
    """
    依赖工厂：校验当前用户拥有指定权限。
    用法： deps=[Depends(require_permissions("graph:write"))]
    """

    async def _checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        user_perms = set(current_user.permissions)
        checks = [has_permission(user_perms, c) for c in codes]
        ok = all(checks) if require_all else any(checks)
        if not ok:
            raise ForbiddenError(
                "权限不足", detail={"required": list(codes), "require_all": require_all}
            )
        return current_user

    return _checker


async def require_super_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if not current_user.is_super_admin:
        raise ForbiddenError("仅超级管理员可执行此操作")
    return current_user


async def require_tenant_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if current_user.system_role not in (
        SystemRole.SUPER_ADMIN.value,
        SystemRole.TENANT_ADMIN.value,
    ):
        raise ForbiddenError("需要租户管理员权限")
    return current_user


# ---------------- 项目级 API Key 认证（OpenClaw / 龙虾 SDK）----------------
@dataclass
class APIKeyPrincipal:
    """以项目 API Key 认证的服务主体（无具体用户）。"""
    project: Project
    api_key: ProjectAPIKey

    @property
    def project_id(self) -> str:
        return self.project.id

    @property
    def tenant_id(self) -> str:
        return self.project.tenant_id


async def get_project_api_principal(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> APIKeyPrincipal:
    """
    解析项目级 API Key（cz_live_...），用于 OpenClaw 远程记忆接入等无登录态场景。
    自动写入 tenant/project 隔离上下文，并刷新 last_used_at。
    """
    if not x_api_key:
        raise UnauthorizedError("缺少 X-API-Key")
    key_hash = hash_api_key(x_api_key)
    api_key = await db.scalar(
        select(ProjectAPIKey).where(ProjectAPIKey.key_hash == key_hash)
    )
    if api_key is None or not api_key.is_active:
        raise UnauthorizedError("无效或已停用的 API Key")
    now = datetime.now(timezone.utc)
    if api_key.expires_at and api_key.expires_at < now:
        raise UnauthorizedError("API Key 已过期")

    project = await db.get(Project, api_key.project_id)
    if project is None:
        raise NotFoundError("API Key 关联的项目不存在")

    api_key.last_used_at = now
    ctx.set_tenant_id(project.tenant_id)
    ctx.set_project_id(project.id)

    return APIKeyPrincipal(project=project, api_key=api_key)
