"""时序数据清理任务。"""
import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete

from core.celery_app import celery_app
from core.config import settings

logger = structlog.get_logger(__name__)


async def _cleanup() -> dict:
    """
    清理逻辑：按保留期清理过期审计日志。
    （时序冲突消解在写入路径实时进行，见 TemporalEngine.resolve_conflict_keep_latest）
    """
    from core.database import AsyncSessionLocal
    from models.audit import AuditLog

    removed_audit = 0
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=settings.audit_log_retention_days
        )
        result = await db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
        removed_audit = result.rowcount or 0
        await db.commit()

    logger.info("cleanup done", removed_audit=removed_audit)
    return {"removed_audit": removed_audit}


@celery_app.task(name="core.tasks.cleanup_tasks.cleanup_expired_data")
def cleanup_expired_data() -> dict:
    """清理已过期的时序数据 / 审计日志（定时任务）。"""
    return asyncio.run(_cleanup())
