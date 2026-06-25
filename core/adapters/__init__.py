"""存储层适配器：后端按 STORAGE_BACKEND 选择。

  postgres   → pgvector(向量) + AGE(图，当前状态遍历) + PG 镜像表(时序遍历)
  kuzu_chroma→ Chroma(向量) + Kuzu(图) + PG 镜像表（旧后端）
"""
from core.config import settings
from core.adapters.chroma_adapter import ChromaAdapter, chroma_adapter
from core.adapters.embedding import EmbeddingAdapter, embedding_adapter
from core.adapters.graph_repo import PGGraphRepository, pg_graph_repo
from core.adapters.kuzu_adapter import KuzuAdapter, kuzu_adapter
from core.adapters.object_storage import ObjectStorageAdapter, object_storage
from core.adapters.pgvector_adapter import PgVectorAdapter, pgvector_adapter
from core.adapters.age_adapter import AgeAdapter, age_adapter


def get_vector_adapter():
    """按后端返回向量适配器（接口一致，drop-in）。"""
    if settings.storage_backend == "postgres":
        return pgvector_adapter
    return chroma_adapter


def get_age_adapter():
    """返回 AGE 图适配器（仅 postgres 后端有意义）。"""
    return age_adapter


__all__ = [
    "ChromaAdapter", "chroma_adapter",
    "EmbeddingAdapter", "embedding_adapter",
    "PGGraphRepository", "pg_graph_repo",
    "KuzuAdapter", "kuzu_adapter",
    "ObjectStorageAdapter", "object_storage",
    "PgVectorAdapter", "pgvector_adapter",
    "AgeAdapter", "age_adapter",
    "get_vector_adapter", "get_age_adapter",
]
