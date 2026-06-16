"""Project 项目 schema。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.common import ORMModel


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    description: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = Field(default=None, description="项目级 LLM Key，将加密存储")
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, description="active|archived")
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None


class ProjectOut(ORMModel):
    id: str
    tenant_id: str
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    kuzu_graph_name: str
    chroma_collection_name: str
    entity_count: int
    relation_count: int
    episode_count: int
    memory_tree_node_count: int
    created_at: datetime
    updated_at: datetime


class ProjectAPIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expires_at: Optional[datetime] = None


class ProjectAPIKeyOut(ORMModel):
    id: str
    project_id: str
    name: str
    key_prefix: str
    is_active: bool
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
