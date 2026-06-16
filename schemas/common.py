"""通用 Pydantic 基础类型：统一响应、分页、时序参数。"""
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """可从 SQLAlchemy ORM 对象解析的基类。"""
    model_config = ConfigDict(from_attributes=True)


class APIResponse(BaseModel, Generic[T]):
    """统一成功响应包装。"""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    items: List[T] = Field(default_factory=list)
    meta: PageMeta


class TemporalParams(BaseModel):
    """时序查询参数：用于「任意时间点快照」与时间范围过滤。"""
    as_of: Optional[datetime] = Field(
        default=None, description="时间点快照：仅返回该时刻有效的数据"
    )
    valid_from_gte: Optional[datetime] = Field(default=None, description="生效时间下界")
    valid_from_lte: Optional[datetime] = Field(default=None, description="生效时间上界")
    include_expired: bool = Field(
        default=False, description="是否包含已失效（valid_until 已过）的数据"
    )


class TemporalFields(BaseModel):
    """时序字段统一输出。"""
    valid_from: datetime
    valid_until: Optional[datetime] = None
    version: int
    source: str
