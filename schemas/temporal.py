"""时序工作台 schema：快照、差异对比、生命周期链路。"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SnapshotRequest(BaseModel):
    """生成某时间点的全项目知识快照。"""
    as_of: datetime = Field(description="快照时间点")
    include_entities: bool = True
    include_relations: bool = True
    include_memory_tree: bool = False


class SnapshotStats(BaseModel):
    entity_count: int = 0
    relation_count: int = 0
    memory_tree_node_count: int = 0


class SnapshotResponse(BaseModel):
    project_id: str
    as_of: datetime
    stats: SnapshotStats
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    relations: List[Dict[str, Any]] = Field(default_factory=list)
    memory_tree_nodes: List[Dict[str, Any]] = Field(default_factory=list)


class SnapshotDiffRequest(BaseModel):
    """两个时间点快照差异对比。"""
    from_time: datetime
    to_time: datetime
    include_entities: bool = True
    include_relations: bool = True


class DiffItem(BaseModel):
    change_type: str = Field(description="added|removed|modified")
    kind: str = Field(description="entity|relation")
    id: str
    name: Optional[str] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None


class SnapshotDiffResponse(BaseModel):
    project_id: str
    from_time: datetime
    to_time: datetime
    added: int = 0
    removed: int = 0
    modified: int = 0
    changes: List[DiffItem] = Field(default_factory=list)


class EntityLifecycleRequest(BaseModel):
    """单实体全生命周期变更链路。"""
    entity_kuzu_uuid: Optional[str] = None
    entity_name: Optional[str] = None


class LifecycleEvent(BaseModel):
    version: int
    valid_from: datetime
    valid_until: Optional[datetime] = None
    source: str
    summary: Optional[str] = None
    change: str = Field(description="created|updated|expired")
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class EntityLifecycleResponse(BaseModel):
    entity_name: Optional[str] = None
    entity_kuzu_uuid: Optional[str] = None
    total_versions: int = 0
    events: List[LifecycleEvent] = Field(default_factory=list)
