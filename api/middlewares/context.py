"""
请求上下文中间件
================
1. 为每个请求分配 request_id（透传 X-Request-ID 或新生成）
2. 读取 X-Tenant-ID / X-Project-ID 头写入 contextvars（供数据层隔离）
3. 绑定 structlog contextvars，日志自动携带 request_id/tenant/project
4. 响应回写 X-Request-ID
"""
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core import context as ctx


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        tenant_id = request.headers.get("X-Tenant-ID")
        project_id = request.headers.get("X-Project-ID")

        ctx.set_request_id(request_id)
        ctx.set_tenant_id(tenant_id)
        ctx.set_project_id(project_id)
        ctx.set_user_id(None)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            tenant_id=tenant_id,
            project_id=project_id,
            path=request.url.path,
        )

        # 存入 request.state 便于依赖读取
        request.state.request_id = request_id
        request.state.header_tenant_id = tenant_id
        request.state.header_project_id = project_id

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers["X-Request-ID"] = request_id
        return response
