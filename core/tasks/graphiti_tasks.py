"""Graphiti 抽取异步任务。"""
import asyncio

import structlog

from core.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _process(episode_id: str) -> dict:
    from core.database import AsyncSessionLocal
    from core.services.graphiti_orchestrator import graphiti_orchestrator

    async with AsyncSessionLocal() as db:
        result = await graphiti_orchestrator.ingest_episode(db, episode_id)
        await db.commit()
        return result


@celery_app.task(
    name="core.tasks.graphiti_tasks.process_episode", bind=True, max_retries=3
)
def process_episode(self, episode_id: str) -> dict:
    """异步处理单条 Episode：实体抽取 → 时序打标 → 分发存储。"""
    try:
        return asyncio.run(_process(episode_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("process_episode retry", episode_id=episode_id, error=str(exc))
        raise self.retry(exc=exc, countdown=10)
