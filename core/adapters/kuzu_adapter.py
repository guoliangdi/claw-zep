"""
Kuzu 图数据库适配器
====================
封装对 Kuzu 的原生连接与 Cypher 执行。Graphiti 通过其 KuzuDriver 写入图数据，
本适配器提供项目级只读查询入口（大规模原生图算法、跨实体路径等）。

Kuzu 为嵌入式数据库：每个项目使用独立 db 目录实现物理隔离。
未安装 kuzu / 目录不存在时方法安全返回空，调用方可回退至 PGGraphRepository。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from core.config import settings

logger = structlog.get_logger(__name__)


class KuzuAdapter:
    def __init__(self) -> None:
        self._conns: Dict[str, Any] = {}

    def _db_path(self, graph_name: str) -> str:
        return f"{settings.kuzu_db_path}/{graph_name}"

    def _get_conn(self, graph_name: str) -> Optional[Any]:
        if graph_name in self._conns:
            return self._conns[graph_name]
        try:
            import kuzu

            db = kuzu.Database(self._db_path(graph_name))
            conn = kuzu.Connection(db)
            self._conns[graph_name] = conn
            return conn
        except Exception as exc:  # noqa: BLE001
            logger.warning("kuzu unavailable", graph=graph_name, error=str(exc))
            return None

    def execute(self, graph_name: str, cypher: str, params: Optional[dict] = None) -> List[dict]:
        """执行 Cypher，返回行 dict 列表。失败/不可用返回空列表。"""
        conn = self._get_conn(graph_name)
        if conn is None:
            return []
        try:
            result = conn.execute(cypher, parameters=params or {})
            rows: List[dict] = []
            cols = result.get_column_names()
            while result.has_next():
                rows.append(dict(zip(cols, result.get_next())))
            return rows
        except Exception as exc:  # noqa: BLE001
            logger.warning("kuzu query failed", error=str(exc), cypher=cypher[:120])
            return []

    def health(self, graph_name: str) -> bool:
        return self._get_conn(graph_name) is not None

    def close(self) -> None:
        self._conns.clear()


kuzu_adapter = KuzuAdapter()
