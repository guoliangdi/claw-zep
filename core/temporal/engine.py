"""
全局时序引擎
============
对所有挂载 TemporalMixin 的实体（Episode / GraphEntityMeta / GraphRelationMeta /
MemoryTreeNode / Ontology）提供统一的双时序能力：

  · 时序过滤   —— 任意时间点 "有效" 行的查询条件
  · 失效/过期   —— 标记某行在某时刻失效
  · 冲突消解   —— 同一逻辑实体新版本到来时，自动失效旧版本（保留历史行）
  · 版本回溯   —— 列出某逻辑实体的全部历史版本
  · 快照生成   —— 某时间点全项目有效数据
  · 历史回滚   —— 将逻辑实体回滚到指定历史版本（作为新版本写入）

设计要点
--------
每个逻辑实体由「逻辑键」标识（如实体的 kuzu_uuid、关系的 kuzu_uuid）。
一次变更 = 旧版本行 valid_until 置为变更时刻 + 写入一条新版本行（version+1，
valid_from=变更时刻，valid_until=NULL）。因此历史以「行」而非「字段」保留，
支持任意时间点快照与精确回溯（Palantir 风格 bitemporal）。
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Optional, Sequence, Type, TypeVar

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from core.exceptions import NotFoundError, TemporalConflictError

T = TypeVar("T")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TemporalEngine:
    """无状态工具集合；所有方法接收显式 db 会话。"""

    # ---------------- 时序过滤 ----------------
    @staticmethod
    def active_conditions(model: Type[Any], as_of: Optional[datetime] = None):
        """构造『在 as_of 时刻有效』的过滤条件列表。as_of 缺省=当前时间。"""
        ts = as_of or utcnow()
        return [
            model.valid_from <= ts,
            or_(model.valid_until.is_(None), model.valid_until > ts),
        ]

    @classmethod
    def apply_temporal_filter(
        cls,
        stmt: Select,
        model: Type[Any],
        as_of: Optional[datetime] = None,
        include_expired: bool = False,
    ) -> Select:
        """对查询追加时序过滤。include_expired=True 时返回全部历史行。"""
        if include_expired:
            return stmt
        return stmt.where(and_(*cls.active_conditions(model, as_of)))

    # ---------------- 失效 / 过期 ----------------
    @staticmethod
    async def expire(
        db: AsyncSession,
        row: Any,
        at: Optional[datetime] = None,
    ) -> Any:
        """将单行标记失效（in-place）。"""
        if row.valid_until is None:
            row.valid_until = at or utcnow()
        await db.flush()
        return row

    @classmethod
    async def expire_logical(
        cls,
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
        at: Optional[datetime] = None,
    ) -> int:
        """失效某逻辑实体当前有效的全部行。返回失效行数。"""
        ts = at or utcnow()
        stmt = select(model).where(
            getattr(model, logical_key) == logical_value,
            model.project_id == project_id,
            model.valid_until.is_(None),
        )
        rows = (await db.scalars(stmt)).all()
        for r in rows:
            r.valid_until = ts
        await db.flush()
        return len(rows)

    # ---------------- 冲突消解 / 新版本 ----------------
    @classmethod
    async def supersede(
        cls,
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
        new_attrs: dict[str, Any],
        valid_from: Optional[datetime] = None,
        source: str = "system",
    ) -> Any:
        """
        以新版本取代逻辑实体的当前版本：
          1. 失效当前有效行（valid_until=ts）
          2. 写入新行（version=旧max+1, valid_from=ts, valid_until=NULL）
        """
        ts = valid_from or utcnow()

        current = await cls.get_current(db, model, logical_key, logical_value, project_id)
        max_version = await cls._max_version(db, model, logical_key, logical_value, project_id)

        if current is not None:
            current.valid_until = ts

        attrs = dict(new_attrs)
        attrs.setdefault(logical_key, logical_value)
        attrs["project_id"] = project_id
        attrs["valid_from"] = ts
        attrs["valid_until"] = None
        attrs["version"] = (max_version or 0) + 1
        attrs["source"] = source
        new_row = model(**attrs)
        db.add(new_row)
        await db.flush()
        return new_row

    @staticmethod
    async def _max_version(
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
    ) -> Optional[int]:
        from sqlalchemy import func

        return await db.scalar(
            select(func.max(model.version)).where(
                getattr(model, logical_key) == logical_value,
                model.project_id == project_id,
            )
        )

    @classmethod
    async def detect_conflict(
        cls,
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
    ) -> Sequence[Any]:
        """返回同一逻辑实体当前『重叠有效』的多行（>1 即冲突）。"""
        stmt = select(model).where(
            getattr(model, logical_key) == logical_value,
            model.project_id == project_id,
            model.valid_until.is_(None),
        )
        return (await db.scalars(stmt)).all()

    @classmethod
    async def resolve_conflict_keep_latest(
        cls,
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
    ) -> int:
        """
        冲突消解策略『保留最新』：
        当一个逻辑实体存在多条 valid_until IS NULL 行时，
        仅保留 version 最大者，其余失效。返回被失效的行数。
        """
        rows = list(
            await cls.detect_conflict(db, model, logical_key, logical_value, project_id)
        )
        if len(rows) <= 1:
            return 0
        rows.sort(key=lambda r: (r.version, r.valid_from), reverse=True)
        keep = rows[0]
        ts = utcnow()
        expired = 0
        for r in rows[1:]:
            if r.id != keep.id:
                r.valid_until = ts
                expired += 1
        await db.flush()
        return expired

    # ---------------- 当前版本 / 历史 ----------------
    @classmethod
    async def get_current(
        cls,
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
    ) -> Optional[Any]:
        stmt = (
            select(model)
            .where(
                getattr(model, logical_key) == logical_value,
                model.project_id == project_id,
                model.valid_until.is_(None),
            )
            .order_by(model.version.desc())
            .limit(1)
        )
        return await db.scalar(stmt)

    @classmethod
    async def get_history(
        cls,
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
    ) -> Sequence[Any]:
        """逻辑实体的全部版本，按 version 升序。"""
        stmt = (
            select(model)
            .where(
                getattr(model, logical_key) == logical_value,
                model.project_id == project_id,
            )
            .order_by(model.version.asc())
        )
        return (await db.scalars(stmt)).all()

    # ---------------- 快照 ----------------
    @classmethod
    async def snapshot(
        cls,
        db: AsyncSession,
        model: Type[Any],
        project_id: str,
        as_of: datetime,
        extra_where: Optional[list] = None,
    ) -> Sequence[Any]:
        """返回 as_of 时刻该 model 在项目内有效的全部行。"""
        stmt = select(model).where(model.project_id == project_id)
        stmt = cls.apply_temporal_filter(stmt, model, as_of=as_of)
        if extra_where:
            stmt = stmt.where(*extra_where)
        return (await db.scalars(stmt)).all()

    # ---------------- 回滚 ----------------
    _SKIP_COPY = {"id", "created_at", "updated_at", "valid_from", "valid_until", "version"}

    @classmethod
    async def rollback_to_version(
        cls,
        db: AsyncSession,
        model: Type[Any],
        logical_key: str,
        logical_value: str,
        project_id: str,
        target_version: int,
    ) -> Any:
        """
        将逻辑实体回滚到指定历史版本：把目标版本的业务字段作为『新版本』写入，
        并失效当前版本。保留完整审计链（不删除历史行）。
        """
        history = await cls.get_history(db, model, logical_key, logical_value, project_id)
        target = next((r for r in history if r.version == target_version), None)
        if target is None:
            raise NotFoundError(
                "目标版本不存在",
                detail={"logical_value": logical_value, "version": target_version},
            )
        # 拷贝目标版本的业务字段
        new_attrs: dict[str, Any] = {}
        for col in model.__table__.columns.keys():
            if col in cls._SKIP_COPY or col in ("project_id",):
                continue
            new_attrs[col] = getattr(target, col)
        return await cls.supersede(
            db, model, logical_key, logical_value, project_id,
            new_attrs=new_attrs, source="rollback",
        )


temporal_engine = TemporalEngine()
