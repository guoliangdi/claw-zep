"""存储层适配器：Kuzu 图库 / Chroma 向量 / 对象存储 / PG 图仓储 / Embedding。"""
from core.adapters.chroma_adapter import ChromaAdapter, chroma_adapter
from core.adapters.embedding import EmbeddingAdapter, embedding_adapter
from core.adapters.graph_repo import PGGraphRepository, pg_graph_repo
from core.adapters.kuzu_adapter import KuzuAdapter, kuzu_adapter
from core.adapters.object_storage import ObjectStorageAdapter, object_storage

__all__ = [
    "ChromaAdapter",
    "chroma_adapter",
    "EmbeddingAdapter",
    "embedding_adapter",
    "PGGraphRepository",
    "pg_graph_repo",
    "KuzuAdapter",
    "kuzu_adapter",
    "ObjectStorageAdapter",
    "object_storage",
]
