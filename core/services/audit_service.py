"""
审计日志服务
============
统一写入审计记录。全链路增删改查、配置变更均经此落库。
"""
from __future__ import annotations

import json
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core import context as ctx
from core.config import settings
from models.audit import AuditLog

logger = structlog.get_logger(__name__)


def _safe_json(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    before: Any = None,
    after: Any = None,
    extra: Any = None,
    result: str = "success",
    error_message: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[AuditLog]:
    if not settings.audit_log_enabled:
        return None
    log = AuditLog(
        tenant_id=tenant_id or ctx.get_tenant_id(),
        project_id=project_id or ctx.get_project_id(),
        user_id=user_id or ctx.get_user_id(),
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_json=_safe_json(before),
        after_json=_safe_json(after),
        extra_json=_safe_json(extra),
        result=result,
        error_message=error_message,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=ctx.get_request_id(),
    )
    db.add(log)
    await db.flush()
    return log
