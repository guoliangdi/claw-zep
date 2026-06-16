"""记忆读写与检索 schema（对标 Zep memory add / search）。"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.graph import EntityOut, RelationOut


class MessageIn(BaseModel):
    role: str = Field(description="user|assistant|system")
    content: str
    name: Optional[str] = None
    timestamp: Optional[datetime] = Field(
        default=None, description="消息业务时间，缺省取入库时间"
    )


class MemoryAddRequest(BaseModel):
    """写入记忆：可为对话消息或纯文本/JSON。"""
    content: Optional[str] = Field(default=None, description="纯文本/JSON 内容")
    messages: Optional[List[MessageIn]] = Field(default=None, description="对话消息列表")
    episode_type: str = Field(default="text", description="message|text|json|fact_triple")
    name: Optional[str] = None
    source: str = Field(default="user_input")
    group_id: Optional[str] = Field(default=None, description="会话/批次分组标识")
    valid_from: Optional[datetime] = Field(
        default=None, description="事件业务生效时间（非入库时间）"
    )
    sync: bool = Field(
        default=False, description="true=同步抽取并返回结果；false=异步入队（默认）"
    )


class MemoryAddResponse(BaseModel):
    episode_id: str
    status: str
    task_id: Optional[str] = None
    extracted_entities: int = 0
    extracted_relations: int = 0


class SearchRequest(BaseModel):
    """混合检索请求。"""
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    # 时序过滤
    as_of: Optional[datetime] = Field(default=None, description="时间点快照检索")
    include_expired: bool = False
    # 权重（混合重排）
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    graph_weight: float = Field(default=0.3, ge=0, le=1)
    tree_weight: float = Field(default=0.2, ge=0, le=1)
    # 检索范围
    search_entities: bool = True
    search_relations: bool = True
    search_memory_tree: bool = True
    group_id: Optional[str] = None


class SearchResultItem(BaseModel):
    kind: str = Field(description="entity|relation|memory_tree")
    id: str
    score: float
    title: str
    content: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem] = Field(default_factory=list)
    entities: List[EntityOut] = Field(default_factory=list)
    relations: List[RelationOut] = Field(default_factory=list)
    total: int = 0
    elapsed_ms: float = 0.0
