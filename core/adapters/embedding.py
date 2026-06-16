"""
Embedding 适配器
================
统一文本向量化接口。优先调用配置的 Embedding 服务（OpenAI 兼容，
支持私有化 base_url，如本地 vLLM / Qwen / 智谱）；不可用时退化为
确定性哈希伪向量，保证离线检索链路可运行（自主可控）。
"""
from __future__ import annotations

import hashlib
import math
from typing import List

import structlog

from core.config import settings

logger = structlog.get_logger(__name__)


def _hash_embed(text: str, dim: int) -> List[float]:
    """确定性伪向量：对 token 做哈希散列到固定维度并归一化。"""
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class EmbeddingAdapter:
    def __init__(self) -> None:
        self._client = None
        self.dim = settings.embedding_dimension

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=settings.embedding_api_key or "sk-noop",
                base_url=settings.embedding_base_url,
            )
        return self._client

    async def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if not settings.embedding_api_key:
            return [_hash_embed(t, self.dim) for t in texts]
        try:
            client = self._get_client()
            resp = await client.embeddings.create(
                model=settings.embedding_model, input=texts
            )
            return [d.embedding for d in resp.data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding api failed, fallback hash", error=str(exc))
            return [_hash_embed(t, self.dim) for t in texts]

    async def embed_one(self, text: str) -> List[float]:
        return (await self.embed([text]))[0]


embedding_adapter = EmbeddingAdapter()
