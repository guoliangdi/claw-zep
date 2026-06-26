"""图谱 schema：Episode、实体、关系、图谱可视化。"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.common import ORMModel, TemporalFields


class EpisodeOut(ORMModel):
    id: str
    tenant_id: str
    project_id: str
    graphiti_uuid: Optional[str] = None
    name: Optional[str] = None
    content: str
    episode_type: str
    source_description: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    extracted_entity_count: int
    extracted_relation_count: int
    group_id: Optional[str] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    version: int
    source: str
    created_at: datetime


class EpisodeFilter(BaseModel):
    """Episodes 多条件筛选（来源/状态/时间）。"""
    status: Optional[str] = None
    episode_type: Optional[str] = None
    source: Optional[str] = None
    group_id: Optional[str] = None
    valid_from_gte: Optional[datetime] = None
    valid_from_lte: Optional[datetime] = None
    search: Optional[str] = Field(default=None, description="内容关键词")


class EntityOut(ORMModel):
    id: str
    project_id: str
    kuzu_uuid: str
    name: str
    entity_type: str
    summary: Optional[str] = None
    attributes_json: Optional[str] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    version: int
    source: str
    created_at: datetime


class RelationOut(ORMModel):
    id: str
    project_id: str
    kuzu_uuid: str
    relation_type: str
    fact: Optional[str] = None
    source_entity_kuzu_uuid: str
    target_entity_kuzu_uuid: str
    source_entity_name: Optional[str] = None
    target_entity_name: Optional[str] = None
    confidence_score: Optional[float] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    version: int
    created_at: datetime


# ---- 图谱可视化（Cytoscape 友好格式）----
class GraphNode(BaseModel):
    id: str            # kuzu_uuid
    label: str         # name
    type: str          # entity_type
    summary: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class GraphEdge(BaseModel):
    id: str
    source: str        # source kuzu_uuid
    target: str        # target kuzu_uuid
    label: str         # relation_type
    fact: Optional[str] = None
    confidence_score: Optional[float] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class GraphVisualization(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
