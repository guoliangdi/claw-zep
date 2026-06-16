"""
OpenClaw 云端记忆插件（客户端）
================================
将此模块接入 OpenClaw，替换其原生本地文件记忆存储，实现：
  · 记忆云端统一存储（claw-zep 时序知识中台）
  · 多设备 / 跨端同步
  · 语义检索增强（混合检索：向量 + 图谱 + 记忆树）

仅依赖 httpx。以『项目级 API Key』鉴权。

用法
----
    from openclaw_cloud_memory import CloudMemory

    mem = CloudMemory(
        base_url="https://claw-zep.yourcompany.com",
        api_key="cz_live_xxx",
        device_id="laptop-01",
    )
    mem.remember("用户偏好深色主题", group_id="prefs")
    hits = mem.search("主题偏好")
    mem.save_document("profile", "# 用户画像\n喜欢深色主题")
    doc = mem.load_document("profile")
    changes = mem.sync(since=last_sync_iso)
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise ImportError("openclaw_cloud_memory 需要 httpx：pip install httpx") from exc


class CloudMemoryError(Exception):
    pass


class CloudMemory:
    """同步客户端（适配 OpenClaw 同步调用场景）。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        device_id: Optional[str] = None,
        timeout: float = 30.0,
        api_prefix: str = "/api/v1/openclaw",
    ) -> None:
        self.base = base_url.rstrip("/") + api_prefix
        self.device_id = device_id or "default"
        self._client = httpx.Client(
            timeout=timeout,
            headers={"X-API-Key": api_key, "X-Device-ID": self.device_id},
        )

    # ---------------- 内部 ----------------
    def _req(self, method: str, path: str, **kw) -> Any:
        resp = self._client.request(method, f"{self.base}{path}", **kw)
        if resp.status_code >= 400:
            raise CloudMemoryError(f"{resp.status_code}: {resp.text}")
        return resp.json()

    # ---------------- 身份 ----------------
    def whoami(self) -> Dict[str, Any]:
        return self._req("GET", "/whoami")

    # ---------------- 记忆写入 / 检索 ----------------
    def remember(
        self,
        content: str,
        group_id: Optional[str] = None,
        episode_type: str = "text",
        sync: bool = False,
        valid_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """写入一条记忆（默认异步抽取）。"""
        body: Dict[str, Any] = {
            "content": content,
            "episode_type": episode_type,
            "source": f"openclaw:{self.device_id}",
            "group_id": group_id,
            "sync": sync,
        }
        if valid_from:
            body["valid_from"] = valid_from
        return self._req("POST", "/memory/add", json=body)

    def remember_messages(
        self, messages: List[Dict[str, str]], group_id: Optional[str] = None, sync: bool = False
    ) -> Dict[str, Any]:
        """写入对话消息列表（role/content）。"""
        return self._req(
            "POST", "/memory/add",
            json={"messages": messages, "episode_type": "message",
                  "source": f"openclaw:{self.device_id}", "group_id": group_id, "sync": sync},
        )

    def search(
        self,
        query: str,
        limit: int = 10,
        as_of: Optional[str] = None,
        vector_weight: float = 0.5,
        graph_weight: float = 0.3,
        tree_weight: float = 0.2,
    ) -> List[Dict[str, Any]]:
        """混合检索，返回结果条目列表。"""
        body = {
            "query": query, "limit": limit, "as_of": as_of,
            "vector_weight": vector_weight, "graph_weight": graph_weight,
            "tree_weight": tree_weight,
        }
        data = self._req("POST", "/memory/search", json=body)
        return data.get("results", [])

    # ---------------- 文档（命名记忆，多设备同步）----------------
    def save_document(self, doc_key: str, content_markdown: str, title: Optional[str] = None) -> Dict[str, Any]:
        return self._req(
            "PUT", f"/documents/{doc_key}",
            json={"title": title or doc_key, "content_markdown": content_markdown},
        )

    def load_document(self, doc_key: str) -> Optional[str]:
        data = self._req("GET", f"/documents/{doc_key}")
        return data.get("content_markdown") if data.get("exists") else None

    # ---------------- 多设备增量同步 ----------------
    def sync(self, since: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        return self._req("GET", "/sync", params=params)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CloudMemory":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class AsyncCloudMemory:
    """异步客户端（适配龙虾移动端 Agent / asyncio 环境）。"""

    def __init__(
        self, base_url: str, api_key: str, device_id: Optional[str] = None,
        timeout: float = 30.0, api_prefix: str = "/api/v1/openclaw",
    ) -> None:
        self.base = base_url.rstrip("/") + api_prefix
        self.device_id = device_id or "default"
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"X-API-Key": api_key, "X-Device-ID": self.device_id},
        )

    async def _req(self, method: str, path: str, **kw) -> Any:
        resp = await self._client.request(method, f"{self.base}{path}", **kw)
        if resp.status_code >= 400:
            raise CloudMemoryError(f"{resp.status_code}: {resp.text}")
        return resp.json()

    async def remember(self, content: str, group_id: Optional[str] = None,
                       episode_type: str = "text", sync: bool = False) -> Dict[str, Any]:
        return await self._req("POST", "/memory/add", json={
            "content": content, "episode_type": episode_type,
            "source": f"openclaw:{self.device_id}", "group_id": group_id, "sync": sync})

    async def search(self, query: str, limit: int = 10, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
        data = await self._req("POST", "/memory/search",
                               json={"query": query, "limit": limit, "as_of": as_of})
        return data.get("results", [])

    async def save_document(self, doc_key: str, content_markdown: str, title: Optional[str] = None) -> Dict[str, Any]:
        return await self._req("PUT", f"/documents/{doc_key}",
                               json={"title": title or doc_key, "content_markdown": content_markdown})

    async def load_document(self, doc_key: str) -> Optional[str]:
        data = await self._req("GET", f"/documents/{doc_key}")
        return data.get("content_markdown") if data.get("exists") else None

    async def sync(self, since: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        return await self._req("GET", "/sync", params=params)

    async def aclose(self) -> None:
        await self._client.aclose()


# 兼容 OpenClaw 记忆后端接口的薄封装：替换其本地文件 read/write/append
class OpenClawCloudBackend:
    """
    可作为 OpenClaw `MemoryBackend` 的替代实现。
    将原本写本地文件的 load/save/append 重定向到 claw-zep 云端。
    """

    def __init__(self, cloud: CloudMemory, namespace: str = "openclaw") -> None:
        self.cloud = cloud
        self.namespace = namespace

    def load(self, key: str = "main") -> str:
        return self.cloud.load_document(f"{self.namespace}:{key}") or ""

    def save(self, content: str, key: str = "main") -> None:
        self.cloud.save_document(f"{self.namespace}:{key}", content)

    def append(self, content: str, key: str = "main") -> None:
        existing = self.load(key)
        self.cloud.save_document(f"{self.namespace}:{key}", f"{existing}\n{content}".strip())
        # 同时作为可检索记忆入库
        self.cloud.remember(content, group_id=f"{self.namespace}:{key}")

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.cloud.search(query, limit=limit)
