"""Ontology 本体 schema。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.common import ORMModel


class EntityTypeDef(BaseModel):
    name: str
    description: Optional[str] = None
    properties: List[dict] = Field(
        default_factory=list,
        description='属性定义列表，如 [{"name":"role","type":"str","description":"职位"}]',
    )


class EdgeTypeDef(BaseModel):
    name: str
    description: Optional[str] = None
    source: Optional[str] = Field(default=None, description="源实体类型")
    target: Optional[str] = Field(default=None, description="目标实体类型")
    properties: List[dict] = Field(default_factory=list)


class OntologyUpsert(BaseModel):
    name: str = "default"
    description: Optional[str] = None
    entity_types: List[EntityTypeDef] = Field(default_factory=list)
    edge_types: List[EdgeTypeDef] = Field(default_factory=list)


class OntologyOut(ORMModel):
    id: str
    project_id: str
    name: str
    description: Optional[str] = None
    entity_types: List[EntityTypeDef] = Field(default_factory=list)
    edge_types: List[EdgeTypeDef] = Field(default_factory=list)
    version: int
    is_current: bool
    valid_from: datetime
    valid_until: Optional[datetime] = None
    created_at: datetime
