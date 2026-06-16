"""记忆树 schema：节点 CRUD、树形结构、版本、导出。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.common import ORMModel


class MemoryTreeNodeCreate(BaseModel):
    tree_layer: str = Field(description="source|topic|global")
    title: str = Field(min_length=1, max_length=256)
    content_markdown: Optional[str] = None
    parent_id: Optional[str] = None
    topic_id: Optional[str] = None
    topic_label: Optional[str] = None
    entity_refs: List[str] = Field(default_factory=list, description="关联实体 kuzu_uuid")
    source_episode_id: Optional[str] = None
    order_index: int = 0
    valid_from: Optional[datetime] = None


class MemoryTreeNodeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=256)
    content_markdown: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = Field(default=None, description="active|archived|draft")
    parent_id: Optional[str] = None
    topic_label: Optional[str] = None
    entity_refs: Optional[List[str]] = None
    order_index: Optional[int] = None
    change_summary: Optional[str] = Field(default=None, description="本次编辑说明，记入版本历史")


class MemoryTreeNodeOut(ORMModel):
    id: str
    tenant_id: str
    project_id: str
    tree_layer: str
    status: str
    parent_id: Optional[str] = None
    depth: int
    path: Optional[str] = None
    order_index: int
    title: str
    content_markdown: Optional[str] = None
    summary: Optional[str] = None
    topic_id: Optional[str] = None
    topic_label: Optional[str] = None
    entity_refs: List[str] = Field(default_factory=list)
    source_episode_id: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    word_count: int
    child_count: int
    valid_from: datetime
    valid_until: Optional[datetime] = None
    version: int
    created_at: datetime
    updated_at: datetime


class MemoryTreeNodeTree(MemoryTreeNodeOut):
    """递归树形结构输出。"""
    children: List["MemoryTreeNodeTree"] = Field(default_factory=list)


class MemoryTreeNodeVersionOut(ORMModel):
    id: str
    node_id: str
    version_number: int
    title: str
    content_markdown: Optional[str] = None
    changed_by: Optional[str] = None
    change_summary: Optional[str] = None
    created_at: datetime


class MemoryTreeExportRequest(BaseModel):
    tree_layer: Optional[str] = Field(default=None, description="为空导出全部层")
    format: str = Field(default="obsidian", description="obsidian|markdown|zip")
    include_versions: bool = False


class MemoryTreeExportResponse(BaseModel):
    format: str
    file_count: int
    download_url: Optional[str] = None
    object_key: Optional[str] = None
    content: Optional[str] = Field(default=None, description="单文件导出时直接返回内容")


MemoryTreeNodeTree.model_rebuild()
