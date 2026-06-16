"""
摘要生成
========
LLM 驱动的节点摘要，带离线启发式降级（取首句/截断），保证自主可控。
"""
from __future__ import annotations

import re
from typing import List, Optional

import structlog

from core.config import settings

logger = structlog.get_logger(__name__)

_SENT_SPLIT = re.compile(r"(?<=[。！？.!?])\s*")


def _heuristic_summary(text: str, max_chars: int = 200) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    sentences = [s for s in _SENT_SPLIT.split(text) if s.strip()]
    out = ""
    for s in sentences:
        if len(out) + len(s) > max_chars:
            break
        out += s
    return (out or text[:max_chars]).strip()


async def generate_summary(
    text: str,
    context: Optional[str] = None,
    max_chars: int = 200,
) -> str:
    """生成摘要：优先 LLM，失败/未配置则启发式。"""
    if not settings.llm_api_key:
        return _heuristic_summary(text, max_chars)
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        prompt = (
            "用简洁中文为以下内容生成不超过"
            f"{max_chars}字的摘要，只输出摘要本身：\n\n{text[:4000]}"
        )
        if context:
            prompt = f"背景：{context}\n\n{prompt}"
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=settings.llm_temperature,
            max_tokens=512,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm summary failed, fallback heuristic", error=str(exc))
        return _heuristic_summary(text, max_chars)


async def synthesize_topic_summary(titles_and_summaries: List[str], topic: str) -> str:
    """将多个子节点摘要归纳为主题摘要。"""
    joined = "\n- ".join(titles_and_summaries[:50])
    text = f"主题「{topic}」包含以下要点：\n- {joined}"
    return await generate_summary(text, context=f"主题聚合：{topic}", max_chars=300)
