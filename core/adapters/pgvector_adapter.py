"""
pgvector 向量适配器（storage_backend=postgres）
================================================
用单表 vector_index 存全部向量，按 project_id 过滤实现隔离/融合：
  · 隔离：project_ids = [当前项目]
  · 融合：project_ids = [项目组...]

对外方法与 ChromaAdapter 保持一致（drop-in），便于 orchestrator/retrieval 切换。
pgvector 不可用时回退进程内余弦（继承既有降级哲学）。
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text

from core.adapters.embedding import embedding_adapter
from core.config import settings

logger = structlog.get_logger(__name__)


def _vec_literal(v: List[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def _as_pids(where: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    if not where:
        return None
    pid = where.get("project_id")
    if pid is None:
        return None
    return pid if isinstance(pid, list) else [pid]


class PgVectorAdapter:
    def __init__(self) -> None:
        self._engine = None
        # 内存回退
        self._mem: Dict[str, dict] = {}
        self._ok: Optional[bool] = None

    def _get_engine(self):
        if self._engine is None:
            from core.database import engine
            self._engine = engine
        return self._engine

    # ---------------- 写入 ----------------
    async def upsert(
        self,
        collection: str,            # 兼容签名；实际隔离按 metadata.project_id
        doc_id: str,
        text_content: str,
        metadata: Dict[str, Any],
        session=None,               # 给定则复用调用方事务（Phase C 单事务写入）
    ) -> None:
        vector = await embedding_adapter.embed_one(text_content)
        kind = metadata.get("kind", "entity")
        ref_id = metadata.get("ref_id") or metadata.get("kuzu_uuid") or doc_id
        tenant_id = metadata.get("tenant_id", "")
        project_id = metadata.get("project_id", "")
        vf = metadata.get("valid_from")
        vu = metadata.get("valid_until")
        meta = {k: v for k, v in metadata.items()
                if k not in {"kind", "ref_id", "tenant_id", "project_id", "valid_from", "valid_until"}}

        if not await self._pgvector_ok():
            self._mem[doc_id] = {
                "vector": vector, "text": text_content, "kind": kind, "ref_id": ref_id,
                "project_id": project_id, "tenant_id": tenant_id, "meta": meta,
            }
            return

        sql = text("""
            INSERT INTO vector_index (id, tenant_id, project_id, kind, ref_id, text, embedding, valid_from, valid_until, meta)
            VALUES (:id, :tenant_id, :project_id, :kind, :ref_id, :text, (:emb)::vector, :vf, :vu, (:meta)::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                embedding = EXCLUDED.embedding, text = EXCLUDED.text, meta = EXCLUDED.meta,
                valid_from = EXCLUDED.valid_from, valid_until = EXCLUDED.valid_until
        """)
        params = {
            "id": doc_id, "tenant_id": tenant_id, "project_id": project_id,
            "kind": kind, "ref_id": ref_id, "text": text_content,
            "emb": _vec_literal(vector), "vf": vf, "vu": vu,
            "meta": json.dumps(meta, ensure_ascii=False, default=str),
        }
        if session is not None:
            await session.execute(sql, params)
            return
        eng = self._get_engine()
        async with eng.begin() as conn:
            await conn.execute(sql, params)

    async def upsert_entity(
        self, project, kuzu_uuid: str, name: str, summary: str, tenant_id: str,
        session=None,
    ) -> None:
        await self.upsert(
            project.chroma_collection_name,
            f"entity:{kuzu_uuid}",
            f"{name}. {summary}",
            {"kind": "entity", "ref_id": kuzu_uuid, "name": name,
             "tenant_id": tenant_id, "project_id": project.id},
            session=session,
        )

    # ---------------- 检索 ----------------
    async def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        vector = await embedding_adapter.embed_one(query_text)
        pids = _as_pids(where)
        kind = (where or {}).get("kind")

        if not await self._pgvector_ok():
            return self._mem_query(vector, n_results, pids, kind)

        conds = ["TRUE"]
        params: Dict[str, Any] = {"emb": _vec_literal(vector), "n": n_results}
        if pids:
            conds.append("project_id = ANY(:pids)")
            params["pids"] = pids
        if kind:
            conds.append("kind = :kind")
            params["kind"] = kind
        sql = text(f"""
            SELECT id, ref_id, kind, text, meta, project_id,
                   1 - (embedding <=> (:emb)::vector) AS score
            FROM vector_index
            WHERE {' AND '.join(conds)}
            ORDER BY embedding <=> (:emb)::vector
            LIMIT :n
        """)
        eng = self._get_engine()
        async with eng.connect() as conn:
            rows = (await conn.execute(sql, params)).mappings().all()
        out = []
        for r in rows:
            meta = r["meta"] if isinstance(r["meta"], dict) else json.loads(r["meta"] or "{}")
            meta = {**meta, "kind": r["kind"], "ref_id": r["ref_id"], "project_id": r["project_id"]}
            out.append({"id": r["id"], "score": float(r["score"]),
                        "metadata": meta, "document": r["text"]})
        return out

    async def delete(self, collection: str, doc_id: str) -> None:
        if not await self._pgvector_ok():
            self._mem.pop(doc_id, None)
            return
        eng = self._get_engine()
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM vector_index WHERE id = :id"), {"id": doc_id})

    # ---------------- 内部 ----------------
    async def _pgvector_ok(self) -> bool:
        if self._ok is not None:
            return self._ok
        if not settings.pgvector_enabled:
            self._ok = False
            return False
        try:
            eng = self._get_engine()
            async with eng.connect() as conn:
                await conn.execute(text("SELECT 1 FROM vector_index LIMIT 1"))
            self._ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("pgvector table unavailable, in-memory fallback", error=str(exc))
            self._ok = False
        return self._ok

    @staticmethod
    def _cosine(a, b) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    def _mem_query(self, vector, n, pids, kind) -> List[dict]:
        scored = []
        for _id, it in self._mem.items():
            if pids and it["project_id"] not in pids:
                continue
            if kind and it["kind"] != kind:
                continue
            scored.append((_id, self._cosine(vector, it["vector"]), it))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [{"id": i, "score": s,
                 "metadata": {**it["meta"], "kind": it["kind"], "ref_id": it["ref_id"],
                              "project_id": it["project_id"]},
                 "document": it["text"]} for i, s, it in scored[:n]]


pgvector_adapter = PgVectorAdapter()
