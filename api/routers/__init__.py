"""API 路由聚合。"""
from api.routers import (
    audit,
    auth,
    graph,
    memory,
    memory_tree,
    palantir,
    playground,
    projects,
    rbac,
    tenants,
    temporal,
    users,
    webhooks,
)

__all__ = [
    "audit",
    "auth",
    "graph",
    "memory",
    "memory_tree",
    "palantir",
    "playground",
    "projects",
    "rbac",
    "tenants",
    "temporal",
    "users",
    "webhooks",
]
