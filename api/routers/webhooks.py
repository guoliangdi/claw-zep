"""Webhook 路由：CRUD + 投递记录。"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import ProjectContext, get_db, get_project_context, require_permissions
from core.exceptions import NotFoundError
from core.services.audit_service import write_audit
from models.audit import AuditAction
from models.webhook import Webhook, WebhookDelivery
from schemas.webhook import (
    WebhookCreate,
    WebhookDeliveryOut,
    WebhookOut,
    WebhookUpdate,
)

router = APIRouter(dependencies=[Depends(require_permissions("webhook:manage"))])


def _to_out(w: Webhook) -> WebhookOut:
    return WebhookOut(
        id=w.id, project_id=w.project_id, name=w.name, target_url=w.target_url,
        events=json.loads(w.events_json or "[]"), is_active=w.is_active,
        total_deliveries=w.total_deliveries, failed_deliveries=w.failed_deliveries,
        last_triggered_at=w.last_triggered_at, created_at=w.created_at,
    )


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(
        select(Webhook).where(Webhook.project_id == ctx.project_id)
    )).all()
    return [_to_out(w) for w in rows]


@router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(
    payload: WebhookCreate,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    w = Webhook(
        tenant_id=ctx.tenant_id, project_id=ctx.project_id, name=payload.name,
        target_url=payload.target_url,
        events_json=json.dumps(payload.events, ensure_ascii=False),
        secret=payload.secret, is_active=payload.is_active, created_by=ctx.user.id,
    )
    db.add(w)
    await write_audit(
        db, action=AuditAction.WEBHOOK_CREATE.value, resource_type="webhook",
        resource_id=w.id, after={"url": w.target_url},
    )
    await db.flush()
    return _to_out(w)


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: str, payload: WebhookUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    w = await db.get(Webhook, webhook_id)
    if w is None or w.project_id != ctx.project_id:
        raise NotFoundError("Webhook 不存在")
    data = payload.model_dump(exclude_unset=True)
    if "events" in data:
        w.events_json = json.dumps(data.pop("events"), ensure_ascii=False)
    for k, v in data.items():
        setattr(w, k, v)
    await db.flush()
    return _to_out(w)


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    w = await db.get(Webhook, webhook_id)
    if w is None or w.project_id != ctx.project_id:
        raise NotFoundError("Webhook 不存在")
    await db.delete(w)
    await write_audit(
        db, action=AuditAction.WEBHOOK_DELETE.value, resource_type="webhook",
        resource_id=webhook_id,
    )
    await db.flush()
    return {"success": True}


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    webhook_id: str,
    ctx: ProjectContext = Depends(get_project_context),
    db: AsyncSession = Depends(get_db),
):
    w = await db.get(Webhook, webhook_id)
    if w is None or w.project_id != ctx.project_id:
        raise NotFoundError("Webhook 不存在")
    rows = (await db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc()).limit(100)
    )).all()
    return [WebhookDeliveryOut.model_validate(d) for d in rows]
