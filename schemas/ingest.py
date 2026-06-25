"""
结构化直灌 schema（worldmonitor 等上游推送）
============================================
上游已完成实体/关系抽取，claw-zep 只负责时序打标 + 三库落地，跳过 LLM。
一条 record = 一个源文档/信号，可携带文档正文 + 实体 + 关系三元组。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BulkEntity(BaseModel):
    name: str = Field(min_length=1)
    entity_type: str = "Entity"
    summary: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class BulkRelation(BaseModel):
    source: str = Field(description="源实体名称（须出现在同 record 的 entities 中）")
    relation_type: str
    target: str = Field(description="目标实体名称")
    fact: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    valid_from: Optional[datetime] = None


class BulkRecord(BaseModel):
    source_ref: Optional[Dict[str, Any]] = Field(
        default=None, description="溯源信息，如 {table, id, url}"
    )
    name: Optional[str] = None
    text: Optional[str] = Field(default=None, description="文档正文（可选，作 Episode 留存）")
    valid_from: Optional[datetime] = Field(
        default=None, description="事件/发布时间，时序锚点；缺省取请求级/当前时间"
    )
    entities: List[BulkEntity] = Field(default_factory=list)
    relations: List[BulkRelation] = Field(default_factory=list)


class BulkIngestRequest(BaseModel):
    source: str = Field(default="external", description="来源标签，如 worldmonitor")
    group_id: Optional[str] = None
    default_valid_from: Optional[datetime] = None
    build_memory_tree: bool = Field(
        default=False, description="是否为每条 record 生成记忆树源节点（高吞吐建议关）"
    )
    records: List[BulkRecord] = Field(..., max_length=2000)


class BulkIngestResponse(BaseModel):
    source: str
    project_id: str
    records: int
    episodes: int
    entities: int
    relations: int
    elapsed_ms: float
