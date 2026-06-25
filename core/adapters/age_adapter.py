"""
Apache AGE 图适配器（storage_backend=postgres）
================================================
固定 label 建模（实测决策）：
  · 顶点 label = Entity，属性 {kuzu_uuid, project_id, name, entity_type, version, valid_from, valid_until}
  · 边   label = REL，属性 {project_id, rel_type, fact, confidence, valid_from, valid_until}
  app 角色只做 DML（MERGE/MATCH），label 由部署脚本预建，避免动态建 label 的 owner 权限问题。

隔离/融合：Cypher 中 WHERE n.project_id IN [...]（单值=隔离，多值=融合）。
连接需 search_path 含 ag_catalog；age 已 shared_preload，无需 LOAD。

注意：AGE 投影存「当前状态」图，用于非时序的快速遍历；带 as_of 的时序遍历仍走
PG 镜像表（PGGraphRepository）。两者同库，写入在同一事务，一致性免费。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional, Tuple

import structlog
from sqlalchemy import text

from core.config import settings

logger = structlog.get_logger(__name__)

_SEARCH_PATH = 'SET search_path = ag_catalog, "$user", public'


def _esc(v: Any) -> str:
    """转义为 Cypher 单引号字符串字面量内容。"""
    if v is None:
        return ""
    return str(v).replace("\\", "\\\\").replace("'", "\\'")


def _pid_list(project_ids) -> str:
    pids = project_ids if isinstance(project_ids, list) else [project_ids]
    return "[" + ",".join(f"'{_esc(p)}'" for p in pids) + "]"


def _parse_scalar(v: Any) -> Any:
    """解析 AGE 返回的标量 agtype（字符串带引号 / 数字）。"""
    if v is None:
        return None
    s = str(v)
    # 去掉可能的 ::type 注解
    if "::" in s:
        s = s.rsplit("::", 1)[0]
    try:
        return json.loads(s)
    except Exception:
        return s.strip('"')


class AgeAdapter:
    def __init__(self) -> None:
        self._engine = None
        self._graph = settings.age_graph_name
        self._ok: Optional[bool] = None

    def _get_engine(self):
        if self._engine is None:
            from core.database import engine
            self._engine = engine
        return self._engine

    async def available(self) -> bool:
        if self._ok is not None:
            return self._ok
        if not (settings.storage_backend == "postgres" and settings.age_enabled):
            self._ok = False
            return False
        try:
            eng = self._get_engine()
            async with eng.connect() as conn:
                await conn.execute(text(_SEARCH_PATH))
                n = await conn.scalar(
                    text("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = :g"),
                    {"g": self._graph},
                )
            self._ok = bool(n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AGE unavailable", error=str(exc))
            self._ok = False
        return self._ok

    # 注：Cypher 含大量冒号(:label/{k:v})会被 SQLAlchemy text() 误判为绑定参数；
    # 且 $$ 美元引用需走 asyncpg 简单查询协议。故取底层 asyncpg 连接直发原始 SQL
    # （值已在上层转义内联）。仍共享 SQLAlchemy 事务，保证 Phase C 单事务写入。
    @staticmethod
    async def _raw(conn):
        raw = await conn.get_raw_connection()
        return raw.driver_connection  # asyncpg.Connection

    async def _cypher_write(self, cypher: str, session=None) -> None:
        sql = f"SELECT * FROM cypher('{self._graph}', $$ {cypher} $$) as (v agtype);"
        if session is not None:
            # 复用调用方事务（Phase C 单事务写入：镜像表+AGE+pgvector 同一 commit）
            conn = await session.connection()
            apg = await self._raw(conn)
            await apg.execute(_SEARCH_PATH)
            await apg.execute(sql)
            return
        async with self._get_engine().begin() as conn:
            apg = await self._raw(conn)
            await apg.execute(_SEARCH_PATH)
            await apg.execute(sql)

    async def _cypher_read(self, cypher: str, cols: str) -> List[dict]:
        eng = self._get_engine()
        async with eng.connect() as conn:
            apg = await self._raw(conn)
            await apg.execute(_SEARCH_PATH)
            records = await apg.fetch(
                f"SELECT * FROM cypher('{self._graph}', $$ {cypher} $$) as ({cols});"
            )
        return [dict(r) for r in records]

    # ---------------- 写入（投影当前状态）----------------
    async def upsert_entity(
        self, project_id: str, kuzu_uuid: str, name: str, entity_type: str,
        version: int = 1, valid_from: Optional[datetime] = None, session=None,
    ) -> None:
        vf = _esc(valid_from.isoformat()) if valid_from else ""
        cy = (
            f"MERGE (n:Entity {{kuzu_uuid:'{_esc(kuzu_uuid)}', project_id:'{_esc(project_id)}'}}) "
            f"SET n.name='{_esc(name)}', n.entity_type='{_esc(entity_type)}', "
            f"n.version={int(version)}, n.valid_from='{vf}'"
        )
        await self._cypher_write(cy, session=session)

    async def upsert_relation(
        self, project_id: str, rel_type: str, source_uuid: str, target_uuid: str,
        fact: Optional[str] = None, confidence: Optional[float] = None,
        valid_from: Optional[datetime] = None, session=None,
    ) -> None:
        conf = float(confidence) if confidence is not None else 0.5
        vf = _esc(valid_from.isoformat()) if valid_from else ""
        cy = (
            f"MATCH (a:Entity {{kuzu_uuid:'{_esc(source_uuid)}', project_id:'{_esc(project_id)}'}}), "
            f"(b:Entity {{kuzu_uuid:'{_esc(target_uuid)}', project_id:'{_esc(project_id)}'}}) "
            f"MERGE (a)-[r:REL {{rel_type:'{_esc(rel_type)}', project_id:'{_esc(project_id)}'}}]->(b) "
            f"SET r.fact='{_esc(fact)}', r.confidence={conf}, r.valid_from='{vf}'"
        )
        await self._cypher_write(cy, session=session)

    # ---------------- 遍历（当前状态）----------------
    async def neighbors(
        self, project_ids, kuzu_uuid: str, direction: str = "out",
    ) -> List[Tuple[str, str, str]]:
        """返回 [(rel_type, neighbor_uuid, neighbor_name)]。"""
        pl = _pid_list(project_ids)
        if direction == "out":
            pat = f"(a:Entity {{kuzu_uuid:'{_esc(kuzu_uuid)}'}})-[r:REL]->(b:Entity)"
        elif direction == "in":
            pat = f"(b:Entity)-[r:REL]->(a:Entity {{kuzu_uuid:'{_esc(kuzu_uuid)}'}})"
        else:
            pat = f"(a:Entity {{kuzu_uuid:'{_esc(kuzu_uuid)}'}})-[r:REL]-(b:Entity)"
        cy = (
            f"MATCH {pat} WHERE a.project_id IN {pl} AND b.project_id IN {pl} "
            f"RETURN r.rel_type, b.kuzu_uuid, b.name"
        )
        rows = await self._cypher_read(cy, "rel agtype, nbr agtype, nm agtype")
        return [(_parse_scalar(r["rel"]), _parse_scalar(r["nbr"]), _parse_scalar(r["nm"])) for r in rows]

    async def find_paths(
        self, project_ids, start_uuid: str, max_hops: int = 3, max_paths: int = 20,
    ) -> List[List[dict]]:
        """
        变长路径遍历（当前状态）。AGE 不支持 nodes(p)/list 推导，故 RETURN p 后解析路径 agtype。
        注：边仅在同 project 内创建，故按起止节点 project_id 过滤即保证不跨项目泄漏。
        """
        pl = _pid_list(project_ids)
        cy = (
            f"MATCH p=(a:Entity {{kuzu_uuid:'{_esc(start_uuid)}'}})-[:REL*1..{int(max_hops)}]->(b:Entity) "
            f"WHERE a.project_id IN {pl} AND b.project_id IN {pl} "
            f"RETURN p LIMIT {int(max_paths)}"
        )
        rows = await self._cypher_read(cy, "p agtype")
        paths: List[List[dict]] = []
        for r in rows:
            edges = self._parse_path(r["p"])
            if edges:
                paths.append(edges)
        return paths

    @staticmethod
    def _parse_path(raw: Any) -> List[dict]:
        """解析 AGE path agtype（[vertex,edge,vertex,...]::path）为边序列。"""
        if raw is None:
            return []
        s = str(raw).strip()
        s = s.replace("}::vertex", "}").replace("}::edge", "}").replace("]::path", "]")
        try:
            arr = json.loads(s)
        except Exception:
            return []
        edges: List[dict] = []
        for i in range(1, len(arr), 2):
            e = arr[i]
            frm = arr[i - 1].get("properties", {})
            to = arr[i + 1].get("properties", {}) if i + 1 < len(arr) else {}
            ep = e.get("properties", {})
            edges.append({
                "from": frm.get("kuzu_uuid"), "from_name": frm.get("name"),
                "to": to.get("kuzu_uuid"), "to_name": to.get("name"),
                "relation": ep.get("rel_type"), "fact": ep.get("fact"),
                "confidence": ep.get("confidence"),
            })
        return edges

    async def delete_entity(self, project_id: str, kuzu_uuid: str) -> None:
        cy = (
            f"MATCH (n:Entity {{kuzu_uuid:'{_esc(kuzu_uuid)}', project_id:'{_esc(project_id)}'}}) "
            f"DETACH DELETE n"
        )
        await self._cypher_write(cy)


age_adapter = AgeAdapter()
