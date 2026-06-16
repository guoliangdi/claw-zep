from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import init_db, close_db
from core.redis_client import get_redis, close_redis
from core.logging import setup_logging, get_logger
from core.exceptions import ClawZepException
from api.middlewares import RequestContextMiddleware

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("claw-zep starting", env=settings.app_env)
    await init_db()
    await get_redis()
    # 幂等初始化：权限/系统角色/超级管理员
    from core.database import AsyncSessionLocal
    from core.bootstrap import bootstrap_system
    async with AsyncSessionLocal() as db:
        await bootstrap_system(db)
    logger.info("claw-zep started successfully")
    yield
    logger.info("claw-zep shutting down")
    await close_redis()
    await close_db()


app = FastAPI(
    title="claw-zep",
    description="私有化自主可控时序知识中台 —— 对标Zep，具备Palantir级动态时序知识图谱能力",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# 请求上下文（request_id + 租户/项目隔离上下文）
app.add_middleware(RequestContextMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(ClawZepException)
async def claw_zep_exception_handler(request: Request, exc: ClawZepException) -> JSONResponse:
    logger.warning(
        "business exception",
        error_code=exc.error_code,
        message=exc.message,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": exc.error_code,
            "message": exc.message,
            "detail": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled exception", error=str(exc), path=request.url.path, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "message": "服务内部错误",
        },
    )


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/", tags=["System"])
async def root() -> dict:
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "docs": "/api/docs",
    }


# 路由注册
from api.routers import (
    audit, auth, graph, memory, memory_tree, palantir, playground,
    projects, rbac, tenants, temporal, users, webhooks,
)

API = "/api/v1"
app.include_router(auth.router, prefix=f"{API}/auth", tags=["Auth"])
app.include_router(tenants.router, prefix=f"{API}/tenants", tags=["Tenants"])
app.include_router(projects.router, prefix=f"{API}/projects", tags=["Projects"])
app.include_router(graph.router, prefix=f"{API}/graph", tags=["Graph"])
app.include_router(memory.router, prefix=f"{API}/memory", tags=["Memory"])
app.include_router(temporal.router, prefix=f"{API}/temporal", tags=["Temporal"])
app.include_router(memory_tree.router, prefix=f"{API}/memory-tree", tags=["MemoryTree"])
app.include_router(palantir.router, prefix=f"{API}/palantir", tags=["Palantir"])
app.include_router(playground.router, prefix=f"{API}/playground", tags=["Playground"])
app.include_router(users.router, prefix=f"{API}/users", tags=["Users"])
app.include_router(rbac.router, prefix=f"{API}/rbac", tags=["RBAC"])
app.include_router(webhooks.router, prefix=f"{API}/webhooks", tags=["Webhooks"])
app.include_router(audit.router, prefix=f"{API}/audit", tags=["Audit"])

# OpenClaw 远程记忆接入（项目 API Key 鉴权，阶段10）
try:
    from openclaw_plugin.router import router as openclaw_router

    app.include_router(openclaw_router, prefix=f"{API}/openclaw", tags=["OpenClaw"])
except Exception:  # 插件可选
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_config=None,
    )
