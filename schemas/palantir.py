"""Palantir 企业推演工作台 schema：自然语言问题 → 因果链路推演。"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.graph import GraphVisualization


class ReasoningRequest(BaseModel):
    """自然语言业务问题输入。"""
    question: str = Field(min_length=1, description="业务问题，如『A供应商断供会影响哪些产品线』")
    as_of: Optional[datetime] = Field(default=None, description="基于某时间点的知识推演")
    max_hops: int = Field(default=3, ge=1, le=6, description="因果链路遍历最大跳数")
    max_paths: int = Field(default=20, ge=1, le=100)
    include_memory_tree: bool = True


class CausalPathNode(BaseModel):
    kuzu_uuid: str
    name: str
    entity_type: str


class CausalPathEdge(BaseModel):
    relation_type: str
    fact: Optional[str] = None
    confidence_score: Optional[float] = None


class CausalPath(BaseModel):
    """一条因果传导链路。"""
    nodes: List[CausalPathNode] = Field(default_factory=list)
    edges: List[CausalPathEdge] = Field(default_factory=list)
    score: float = 0.0
    narrative: Optional[str] = Field(default=None, description="链路自然语言解释")


class MemoryTreeEvidence(BaseModel):
    node_id: str
    title: str
    excerpt: Optional[str] = None
    score: float = 0.0


class ReasoningResponse(BaseModel):
    question: str
    answer: str = Field(description="LLM 综合推演结论")
    as_of: Optional[datetime] = None
    seed_entities: List[CausalPathNode] = Field(default_factory=list)
    causal_paths: List[CausalPath] = Field(default_factory=list)
    graph: GraphVisualization = Field(default_factory=GraphVisualization)
    evidence: List[MemoryTreeEvidence] = Field(default_factory=list)
    elapsed_ms: float = 0.0
