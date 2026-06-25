"""
PostgreSQL 扩展与对象初始化（storage_backend=postgres）
========================================================
幂等地准备：
  · pgvector 扩展 + 向量索引表 vector_index（+ HNSW 索引）
  · Apache AGE 扩展 + 图命名空间 claw_graph

任一扩展不可用时记录告警并继续（运行期自动回退：pgvector→内存余弦，AGE→纯 SQL 递归 CTE）。
"""
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from core.config import settings

logger = structlog.get_logger(__name__)


VECTOR_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS vector_index (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- entity | memory_tree | episode
    ref_id      TEXT NOT NULL,          -- 业务逻辑键（实体 kuzu_uuid / 节点 id）
    text        TEXT,
    embedding   vector(%(dim)s),
    valid_from  TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    meta        JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""

VECTOR_INDEX_DDL = [
    # HNSW 余弦相似度索引
    "CREATE INDEX IF NOT EXISTS ix_vector_index_embedding "
    "ON vector_index USING hnsw (embedding vector_cosine_ops) "
    "WITH (m = {m}, ef_construction = {efc});",
    "CREATE INDEX IF NOT EXISTS ix_vector_index_project_kind "
    "ON vector_index (project_id, kind);",
    "CREATE INDEX IF NOT EXISTS ix_vector_index_ref "
    "ON vector_index (project_id, ref_id);",
]


async def _init_pgvector(conn) -> bool:
    try:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        ddl = VECTOR_TABLE_DDL % {"dim": int(settings.embedding_dimension)}
        await conn.execute(text(ddl))
        for stmt in VECTOR_INDEX_DDL:
            await conn.execute(
                text(stmt.format(
                    m=int(settings.pgvector_hnsw_m),
                    efc=int(settings.pgvector_hnsw_ef_construction),
                ))
            )
        logger.info("pgvector ready", dim=settings.embedding_dimension)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("pgvector init failed, will fallback to in-memory", error=str(exc))
        return False


async def _init_age(conn) -> bool:
    try:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS age;"))
        await conn.execute(text("LOAD 'age';"))
        await conn.execute(text('SET search_path = ag_catalog, "$user", public;'))
        graph = settings.age_graph_name
        exists = await conn.scalar(
            text("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = :g"),
            {"g": graph},
        )
        if not exists:
            await conn.execute(text("SELECT create_graph(:g);"), {"g": graph})
        logger.info("AGE ready", graph=graph)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("AGE init failed, will fallback to SQL traversal", error=str(exc))
        return False


async def init_postgres_extensions(engine: AsyncEngine) -> dict:
    """在应用启动时调用（仅 storage_backend=postgres）。返回各扩展可用性。"""
    result = {"pgvector": False, "age": False}
    if settings.storage_backend != "postgres":
        return result
    async with engine.begin() as conn:
        if settings.pgvector_enabled:
            result["pgvector"] = await _init_pgvector(conn)
        if settings.age_enabled:
            result["age"] = await _init_age(conn)
    return result
