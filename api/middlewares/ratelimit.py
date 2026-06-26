"""
限流中间件（per-tenant，Redis 固定窗口）
=========================================
按租户（无则 API Key / 客户端 IP）做每分钟请求数限制，超限返回 429。
Redis 不可用时 fail-open（放行，不阻断业务），符合既有降级哲学。
"""
import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.config import settings

logger = structlog.get_logger(__name__)

_SKIP_PREFIXES = ("/health", "/metrics", "/api/docs", "/api/redoc", "/api/openapi.json")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or path == "/" or path.startswith(_SKIP_PREFIXES):
            return await call_next(request)

        identity = (
            request.headers.get("X-Tenant-ID")
            or request.headers.get("X-API-Key")
            or (request.client.host if request.client else "anon")
        )
        limit = settings.rate_limit_requests_per_minute
        allowed, remaining, retry_after = await self._check(identity, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"success": False, "error_code": "RATE_LIMIT_EXCEEDED",
                         "message": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(retry_after),
                         "X-RateLimit-Limit": str(limit)},
            )
        resp = await call_next(request)
        resp.headers["X-RateLimit-Limit"] = str(limit)
        resp.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        return resp

    @staticmethod
    async def _check(identity: str, limit: int) -> tuple[bool, int, int]:
        """固定窗口计数。返回 (是否放行, 剩余, Retry-After秒)。"""
        try:
            from core.redis_client import get_redis

            redis = await get_redis()
            window = int(time.time()) // 60
            key = f"ratelimit:{identity}:{window}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
            if count > limit:
                return False, 0, 60 - (int(time.time()) % 60)
            return True, limit - count, 0
        except Exception as exc:  # noqa: BLE001  Redis 不可用 → fail-open
            logger.debug("ratelimit fail-open", error=str(exc))
            return True, limit, 0
