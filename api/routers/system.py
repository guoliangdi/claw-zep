"""系统路由：深度就绪检查 + Prometheus 指标。"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from api.middlewares.metrics import render_prometheus
from core.config import settings

router = APIRouter()


@router.get("/health/ready", tags=["System"])
async def readiness() -> dict:
    """依赖深度检查：PostgreSQL / Redis /（postgres 后端）pgvector+AGE。"""
    checks: dict = {}
    overall = True

    # PostgreSQL
    try:
        from core.database import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc}"
        overall = False

    # Redis
    try:
        from core.redis_client import get_redis
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"unavailable: {exc}"  # 非致命

    # pgvector / AGE
    if settings.storage_backend == "postgres":
        try:
            from core.database import engine
            async with engine.connect() as conn:
                exts = (await conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname IN ('vector','age')")
                )).scalars().all()
            checks["pgvector"] = "ok" if "vector" in exts else "missing"
            checks["age"] = "ok" if "age" in exts else "missing(fallback SQL)"
        except Exception as exc:  # noqa: BLE001
            checks["pgvector_age"] = f"error: {exc}"

    return {"status": "ready" if overall else "degraded",
            "storage_backend": settings.storage_backend, "checks": checks}


@router.get("/metrics", response_class=PlainTextResponse, tags=["System"])
async def metrics() -> str:
    return render_prometheus()
