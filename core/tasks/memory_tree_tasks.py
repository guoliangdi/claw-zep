"""记忆树异步任务：周期性主题聚合 + 全局摘要。"""
import asyncio

import structlog
from sqlalchemy import select

from core.celery_app import celery_app
from core.config import settings

logger = structlog.get_logger(__name__)


async def _build_all() -> dict:
    from core.database import AsyncSessionLocal
    from core.memory_tree.builder import memory_tree_builder
    from models.project import Project, ProjectStatus

    built = 0
    async with AsyncSessionLocal() as db:
        projects = (
            await db.scalars(
                select(Project).where(Project.status == ProjectStatus.ACTIVE.value)
            )
        ).all()
        for p in projects:
            try:
                await memory_tree_builder.build_topic_tree(db, p.tenant_id, p.id)
                await memory_tree_builder.build_global_summary(
                    db, p.tenant_id, p.id,
                    period_hours=settings.memory_tree_global_summary_interval_hours,
                )
                await db.commit()
                built += 1
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                logger.error("global summary failed", project_id=p.id, error=str(exc))
    logger.info("global summaries built", projects=built)
    return {"projects": built}


@celery_app.task(name="core.tasks.memory_tree_tasks.build_global_summaries")
def build_global_summaries() -> dict:
    """定时构建全局周期摘要树（含主题聚合）。"""
    return asyncio.run(_build_all())
