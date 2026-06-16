"""
全局双时序模型 TemporalMixin
==============================
所有实体、向量索引记录、记忆树节点强制挂载：
  - valid_from    生效时间（事件发生时间，非入库时间）
  - valid_until   失效时间（NULL=当前有效）
  - version       乐观锁版本号，同 uuid+version 唯一
  - source        数据来源标签（user_input / graphiti_extract / manual / import）
  - created_at    由 UUIDBase 提供，此处不重复

Palantir 时序特性支撑：
  - valid_from/valid_until 构成双时间轴中的"有效时间"维度
  - created_at              构成"事务时间"维度
  - 两维度组合支持任意时间点快照与历史回溯
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column, declared_attr


class TemporalMixin:
    """混入类，不含主键，挂载到 UUIDBase 子类上"""

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="事件/知识生效时间（业务时间轴）",
    )
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="失效时间，NULL 表示当前仍有效",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="版本号，同实体每次更新递增",
    )
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="user_input",
        comment="数据来源：user_input|graphiti_extract|manual|import|system",
    )

    @property
    def is_active(self) -> bool:
        """判断当前时间点是否有效"""
        now = datetime.now(timezone.utc)
        return self.valid_until is None or self.valid_until > now

    def expire(self, at: Optional[datetime] = None) -> None:
        """标记失效"""
        self.valid_until = at or datetime.now(timezone.utc)
        self.version += 1

    def new_version(self, valid_from: Optional[datetime] = None) -> None:
        """创建新版本时调用（先 expire 旧版本，再 new_version 新版本）"""
        self.valid_from = valid_from or datetime.now(timezone.utc)
        self.valid_until = None
        self.version += 1

    @declared_attr
    def __temporal_indexes__(cls):  # noqa
        return (
            Index(f"ix_{cls.__tablename__}_valid_from", "valid_from"),
            Index(f"ix_{cls.__tablename__}_valid_until", "valid_until"),
            Index(f"ix_{cls.__tablename__}_temporal", "valid_from", "valid_until"),
        )
