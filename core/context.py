"""
请求级上下文（contextvars）
============================
承载当前请求的租户/项目/用户标识，供数据访问层自动注入隔离条件，
避免在每一层手动传递 tenant_id/project_id。

中间件在请求入口写入，业务层通过 get_* 读取。
"""
from contextvars import ContextVar
from typing import Optional

_tenant_id: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
_project_id: ContextVar[Optional[str]] = ContextVar("project_id", default=None)
_user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_tenant_id(value: Optional[str]) -> None:
    _tenant_id.set(value)


def get_tenant_id() -> Optional[str]:
    return _tenant_id.get()


def set_project_id(value: Optional[str]) -> None:
    _project_id.set(value)


def get_project_id() -> Optional[str]:
    return _project_id.get()


def set_user_id(value: Optional[str]) -> None:
    _user_id.set(value)


def get_user_id() -> Optional[str]:
    return _user_id.get()


def set_request_id(value: Optional[str]) -> None:
    _request_id.set(value)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def require_tenant_id() -> str:
    tid = _tenant_id.get()
    if not tid:
        from core.exceptions import ForbiddenError

        raise ForbiddenError("缺少租户上下文（X-Tenant-ID）")
    return tid


def require_project_id() -> str:
    pid = _project_id.get()
    if not pid:
        from core.exceptions import ForbiddenError

        raise ForbiddenError("缺少项目上下文（X-Project-ID）")
    return pid
