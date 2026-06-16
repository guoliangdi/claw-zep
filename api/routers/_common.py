"""路由通用工具：分页执行。"""
from __future__ import annotations

from typing import Sequence, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from schemas.common import PageMeta, PaginatedResponse, PaginationParams

T = TypeVar("T")


async def paginate(
    db: AsyncSession,
    stmt: Select,
    params: PaginationParams,
    schema: Type[T],
) -> PaginatedResponse:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.scalar(count_stmt)) or 0
    rows = (
        await db.scalars(stmt.offset(params.offset).limit(params.limit))
    ).all()
    items = [schema.model_validate(r) for r in rows]
    total_pages = (total + params.page_size - 1) // params.page_size
    return PaginatedResponse(
        items=items,
        meta=PageMeta(
            page=params.page,
            page_size=params.page_size,
            total=total,
            total_pages=total_pages,
        ),
    )
