"""
Chroma 向量适配器
==================
按项目维护独立 collection（项目隔离）。封装实体/记忆树文本的向量化写入
与语义检索。Chroma 不可用时退化为进程内余弦相似度内存索引，保证链路可用。

所有向量条目 metadata 携带 tenant_id/project_id/valid_from/valid_until，
检索结果可由上层 TemporalEngine 做时序过滤。
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from core.adapters.embedding import embedding_adapter
from core.config import settings

logger = structlog.get_logger(__name__)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class _MemoryCollection:
    def __init__(self) -> None:
        self.items: Dict[str, dict] = {}

    def upsert(self, _id, vector, metadata, document):
        self.items[_id] = {"vector": vector, "metadata": metadata, "document": document}

    def query(self, vector, n, where: Optional[dict] = None):
        scored = []
        for _id, it in self.items.items():
            if where and not all(it["metadata"].get(k) == v for k, v in where.items()):
                continue
            scored.append((_id, _cosine(vector, it["vector"]), it))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]


class ChromaAdapter:
    def __init__(self) -> None:
        self._client = None
        self._mem: Dict[str, _MemoryCollection] = {}
        self._use_chroma: Optional[bool] = None

    def _client_ok(self) -> bool:
        if self._use_chroma is not None:
            return self._use_chroma
        try:
            import chromadb

            self._client = chromadb.HttpClient(
                host=settings.chroma_host, port=settings.chroma_port
            )
            self._client.heartbeat()
            self._use_chroma = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("chroma unavailable, in-memory vector fallback", error=str(exc))
            self._use_chroma = False
        return self._use_chroma

    def _get_collection(self, name: str):
        if self._client_ok():
            return self._client.get_or_create_collection(name=name)
        if name not in self._mem:
            self._mem[name] = _MemoryCollection()
        return self._mem[name]

    async def upsert(
        self,
        collection: str,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> None:
        vector = await embedding_adapter.embed_one(text)
        col = self._get_collection(collection)
        clean_meta = {k: ("" if v is None else v) for k, v in metadata.items()}
        if self._use_chroma:
            col.upsert(ids=[doc_id], embeddings=[vector], metadatas=[clean_meta], documents=[text])
        else:
            col.upsert(doc_id, vector, clean_meta, text)

    async def upsert_entity(
        self, project, kuzu_uuid: str, name: str, summary: str, tenant_id: str
    ) -> None:
        await self.upsert(
            project.chroma_collection_name,
            f"entity:{kuzu_uuid}",
            f"{name}. {summary}",
            {"kind": "entity", "kuzu_uuid": kuzu_uuid, "name": name,
             "tenant_id": tenant_id, "project_id": project.id},
        )

    async def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        vector = await embedding_adapter.embed_one(query_text)
        col = self._get_collection(collection)
        out: List[dict] = []
        if self._use_chroma:
            res = col.query(query_embeddings=[vector], n_results=n_results, where=where or None)
            ids = (res.get("ids") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            docs = (res.get("documents") or [[]])[0]
            for i, _id in enumerate(ids):
                score = 1.0 - (dists[i] if i < len(dists) else 0.0)
                out.append({"id": _id, "score": score,
                            "metadata": metas[i] if i < len(metas) else {},
                            "document": docs[i] if i < len(docs) else ""})
        else:
            for _id, score, it in col.query(vector, n_results, where):
                out.append({"id": _id, "score": score,
                            "metadata": it["metadata"], "document": it["document"]})
        return out

    async def delete(self, collection: str, doc_id: str) -> None:
        col = self._get_collection(collection)
        if self._use_chroma:
            col.delete(ids=[doc_id])
        else:
            col.items.pop(doc_id, None)


chroma_adapter = ChromaAdapter()
