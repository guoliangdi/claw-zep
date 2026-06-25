from functools import lru_cache
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用基础
    app_name: str = "claw-zep"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = "change-me-in-production-32-chars!!"

    # JWT
    jwt_secret_key: str = "change-me-jwt-secret-32-chars!!!"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "claw_zep"
    postgres_user: str = "claw_zep_user"
    postgres_password: str = "password"
    database_url: str = ""
    database_url_sync: str = ""

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def get_database_url_sync(self) -> str:
        if self.database_url_sync:
            return self.database_url_sync
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_url: str = ""

    def get_redis_url(self) -> str:
        if self.redis_url:
            return self.redis_url
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # Celery
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # 存储后端开关：kuzu_chroma（旧，Kuzu图+Chroma向量）| postgres（新，单PG: AGE图+pgvector）
    # 演进期保留两套实现，验证通过后默认切 postgres
    storage_backend: str = "kuzu_chroma"

    # PostgreSQL 图谱/向量扩展（storage_backend=postgres 时生效）
    age_enabled: bool = True            # Apache AGE 图加速；不可用时自动回退纯 SQL 递归 CTE
    age_graph_name: str = "claw_graph"  # AGE 图命名空间（全租户共享，按 project_id 属性隔离）
    pgvector_enabled: bool = True       # pgvector 向量索引；不可用时回退内存余弦
    pgvector_hnsw_m: int = 16
    pgvector_hnsw_ef_construction: int = 64

    # Kuzu（旧后端）
    kuzu_db_path: str = "./data/kuzu_db"
    kuzu_max_db_size_gb: int = 10

    # Chroma（旧后端）
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_persist_dir: str = "./data/chroma_db"

    # 对象存储
    object_storage_endpoint: str = "localhost:9000"
    object_storage_access_key: str = "minioadmin"
    object_storage_secret_key: str = "minioadmin"
    object_storage_bucket: str = "claw-zep-memory-tree"
    object_storage_use_ssl: bool = False

    # LLM
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.1

    # Embedding
    embedding_provider: str = "openai"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # 多租户
    default_tenant_max_projects: int = 10
    default_tenant_max_users: int = 50
    default_tenant_max_memory_mb: int = 1024
    super_admin_email: str = "admin@claw-zep.com"
    super_admin_password: str = "Admin@123456"

    # 限流
    rate_limit_requests_per_minute: int = 100
    rate_limit_burst: int = 20

    # CORS
    cors_origins: str = '["http://localhost:3000","http://localhost:5173"]'
    cors_allow_credentials: bool = True

    def get_cors_origins(self) -> List[str]:
        try:
            return json.loads(self.cors_origins)
        except Exception:
            return ["http://localhost:3000", "http://localhost:5173"]

    # 审计日志
    audit_log_enabled: bool = True
    audit_log_retention_days: int = 90

    # Graphiti
    graphiti_entity_extraction_enabled: bool = True
    graphiti_relation_extraction_enabled: bool = True
    graphiti_max_episode_batch: int = 50

    # 记忆树
    memory_tree_source_max_depth: int = 5
    memory_tree_topic_max_nodes: int = 200
    memory_tree_global_summary_interval_hours: int = 24
    memory_tree_markdown_export_path: str = "./data/memory_tree_exports"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
