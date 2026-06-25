"""
claw-zep 结构化直灌 SDK（上游推送端，供 worldmonitor 等导入）
============================================================
上游已完成实体/关系抽取后，用本 SDK 把三元组推送到 claw-zep，
claw-zep 负责时序打标 + 图谱/向量/记忆树落地，跳过 LLM。

仅依赖 httpx。以『项目级 API Key』鉴权（cz_live_...）。

最简用法
--------
    from claw_ingest_sdk import ClawIngest

    cz = ClawIngest("https://claw-zep.internal", "cz_live_xxx")
    rec = ClawIngest.record(
        name="signal-123",
        source_ref={"table": "material_public_signals", "id": "123"},
        valid_from="2026-06-01T00:00:00Z",
        entities=[
            ClawIngest.entity("沪硅产业", "Supplier", summary="12寸硅片供应商"),
            ClawIngest.entity("12寸硅片", "Material"),
        ],
        relations=[
            ClawIngest.relation("沪硅产业", "SUPPLIES", "12寸硅片", confidence=0.9),
        ],
    )
    resp = cz.push([rec], source="worldmonitor")   # 自动分批
    print(resp)   # {records, episodes, entities, relations, ...}
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Union

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise ImportError("claw_ingest_sdk 需要 httpx：pip install httpx") from exc

DateLike = Union[str, _dt.datetime, None]


def _iso(v: DateLike) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.isoformat()
    return str(v)


class ClawIngestError(Exception):
    pass


class ClawIngest:
    """同步推送客户端（worldmonitor 为同步 Python）。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 60.0,
        api_prefix: str = "/api/v1/ingest",
    ) -> None:
        self.base = base_url.rstrip("/") + api_prefix
        self._client = httpx.Client(timeout=timeout, headers={"X-API-Key": api_key})

    # ---------------- 载荷构造 helper ----------------
    @staticmethod
    def entity(
        name: str, entity_type: str = "Entity",
        summary: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {"name": name, "entity_type": entity_type,
                "summary": summary, "attributes": attributes or {}}

    @staticmethod
    def relation(
        source: str, relation_type: str, target: str,
        fact: Optional[str] = None, confidence: Optional[float] = None,
        valid_from: DateLike = None,
    ) -> Dict[str, Any]:
        return {"source": source, "relation_type": relation_type, "target": target,
                "fact": fact, "confidence": confidence, "valid_from": _iso(valid_from)}

    @staticmethod
    def record(
        entities: List[Dict[str, Any]],
        relations: Optional[List[Dict[str, Any]]] = None,
        text: Optional[str] = None,
        name: Optional[str] = None,
        valid_from: DateLike = None,
        source_ref: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "name": name, "text": text, "valid_from": _iso(valid_from),
            "source_ref": source_ref, "entities": entities,
            "relations": relations or [],
        }

    # ---------------- 推送 ----------------
    def push(
        self,
        records: List[Dict[str, Any]],
        source: str = "worldmonitor",
        group_id: Optional[str] = None,
        default_valid_from: DateLike = None,
        build_memory_tree: bool = False,
        batch_size: int = 500,
    ) -> Dict[str, Any]:
        """推送 records（自动分批，聚合返回）。"""
        agg = {"records": 0, "episodes": 0, "entities": 0, "relations": 0, "batches": 0}
        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            body = {
                "source": source, "group_id": group_id,
                "default_valid_from": _iso(default_valid_from),
                "build_memory_tree": build_memory_tree, "records": chunk,
            }
            data = self._post("/bulk", body)
            for k in ("records", "episodes", "entities", "relations"):
                agg[k] += int(data.get(k, 0))
            agg["batches"] += 1
        return agg

    def whoami(self) -> Dict[str, Any]:
        """校验 API Key 与项目归属（复用 openclaw whoami）。"""
        resp = self._client.get(self.base.replace("/ingest", "/openclaw") + "/whoami")
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> Dict[str, Any]:
        resp = self._client.post(f"{self.base}{path}", json=body)
        if resp.status_code >= 400:
            raise ClawIngestError(f"{resp.status_code}: {resp.text}")
        return resp.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ClawIngest":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
