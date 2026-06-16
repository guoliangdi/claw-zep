"""项目管理路由：CRUD、API Key、Ontology、成员。"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_current_user,
    get_db,
    get_effective_tenant_id,
    require_permissions,
)
from core.exceptions import ConflictError, ForbiddenError, NotFoundError
from core.security import generate_api_key
from core.services.audit_service import write_audit
from models.audit import AuditAction
from models.ontology import Ontology
from models.project import Project, ProjectAPIKey, ProjectMember, ProjectStatus
from models.tenant import Tenant
from models.user import User
from schemas.auth import CurrentUser
from schemas.ontology import OntologyOut, OntologyUpsert
from schemas.project import (
    ProjectAPIKeyCreate,
    ProjectAPIKeyOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from schemas.user import (
    APIKeyCreateResponse,
    ProjectMemberCreate,
    ProjectMemberOut,
    ProjectMemberUpdate,
)

router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------- 项目 CRUD ----------------
@router.get("", response_model=list[ProjectOut])
async def list_projects(
    current: CurrentUser = Depends(get_current_user),
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Project).where(
        Project.tenant_id == tenant_id, Project.status != ProjectStatus.DELETED.value
    )
    # 普通成员仅看其加入的项目
    if not current.is_super_admin and current.system_role != "tenant_admin":
        member_pids = select(ProjectMember.project_id).where(
            ProjectMember.user_id == current.id
        )
        stmt = stmt.where(Project.id.in_(member_pids))
    stmt = stmt.order_by(Project.created_at.desc())
    rows = (await db.scalars(stmt)).all()
    return [ProjectOut.model_validate(p) for p in rows]


@router.post("", response_model=ProjectOut, status_code=201,
             dependencies=[Depends(require_permissions("project:write"))])
async def create_project(
    payload: ProjectCreate,
    current: CurrentUser = Depends(get_current_user),
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    dup = await db.scalar(
        select(Project).where(
            Project.tenant_id == tenant_id, Project.slug == payload.slug
        )
    )
    if dup:
        raise ConflictError("项目标识在租户内已存在", detail=payload.slug)

    # 配额校验
    tenant = await db.get(Tenant, tenant_id)
    count = len(
        (await db.scalars(select(Project.id).where(Project.tenant_id == tenant_id))).all()
    )
    if tenant and count >= tenant.max_projects:
        raise ForbiddenError("项目数量已达租户配额上限")

    project = Project(
        tenant_id=tenant_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        status=ProjectStatus.ACTIVE.value,
        llm_provider=payload.llm_provider,
        llm_model=payload.llm_model,
        llm_api_key_encrypted=payload.llm_api_key,  # 生产应加密
        embedding_model=payload.embedding_model,
        embedding_dimension=payload.embedding_dimension,
        kuzu_graph_name="pending",
        chroma_collection_name="pending",
    )
    db.add(project)
    await db.flush()
    short = project.id.replace("-", "")[:16]
    project.kuzu_graph_name = f"g_{short}"
    project.chroma_collection_name = f"c_{short}"

    # 创建者成为 owner
    db.add(ProjectMember(project_id=project.id, user_id=current.id,
                         project_role="project_owner"))
    # 默认空本体
    db.add(Ontology(tenant_id=tenant_id, project_id=project.id, name="default",
                    entity_types_json="[]", edge_types_json="[]", is_current=True))

    await write_audit(
        db, action=AuditAction.PROJECT_CREATE.value, tenant_id=tenant_id,
        project_id=project.id, resource_type="project", resource_id=project.id,
        after={"slug": project.slug},
    )
    await db.flush()
    return ProjectOut.model_validate(project)


async def _get_project_in_tenant(db, project_id, tenant_id) -> Project:
    project = await db.get(Project, project_id)
    if project is None or project.tenant_id != tenant_id:
        raise NotFoundError("项目不存在")
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return ProjectOut.model_validate(await _get_project_in_tenant(db, project_id, tenant_id))


@router.patch("/{project_id}", response_model=ProjectOut,
              dependencies=[Depends(require_permissions("project:write"))])
async def update_project(
    project_id: str, payload: ProjectUpdate,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_in_tenant(db, project_id, tenant_id)
    data = payload.model_dump(exclude_unset=True)
    if "llm_api_key" in data:
        project.llm_api_key_encrypted = data.pop("llm_api_key")
    for k, v in data.items():
        setattr(project, k, v)
    await write_audit(
        db, action=AuditAction.PROJECT_UPDATE.value, tenant_id=tenant_id,
        project_id=project.id, resource_type="project", resource_id=project.id, after=data,
    )
    await db.flush()
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", dependencies=[Depends(require_permissions("project:delete"))])
async def delete_project(
    project_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_in_tenant(db, project_id, tenant_id)
    project.status = ProjectStatus.DELETED.value
    await write_audit(
        db, action=AuditAction.PROJECT_DELETE.value, tenant_id=tenant_id,
        project_id=project.id, resource_type="project", resource_id=project.id,
    )
    await db.flush()
    return {"success": True}


# ---------------- API Key ----------------
@router.get("/{project_id}/api-keys", response_model=list[ProjectAPIKeyOut])
async def list_api_keys(
    project_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    rows = (await db.scalars(
        select(ProjectAPIKey).where(ProjectAPIKey.project_id == project_id)
    )).all()
    return [ProjectAPIKeyOut.model_validate(k) for k in rows]


@router.post("/{project_id}/api-keys", response_model=APIKeyCreateResponse, status_code=201,
             dependencies=[Depends(require_permissions("project:write"))])
async def create_api_key(
    project_id: str, payload: ProjectAPIKeyCreate,
    current: CurrentUser = Depends(get_current_user),
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    plain, key_hash, key_prefix = generate_api_key()
    key = ProjectAPIKey(
        project_id=project_id, name=payload.name, key_hash=key_hash,
        key_prefix=key_prefix, expires_at=payload.expires_at, created_by=current.id,
    )
    db.add(key)
    await write_audit(
        db, action=AuditAction.API_KEY_CREATE.value, tenant_id=tenant_id,
        project_id=project_id, resource_type="api_key", resource_id=key.id,
    )
    await db.flush()
    return APIKeyCreateResponse(id=key.id, name=key.name, api_key=plain, key_prefix=key_prefix)


@router.delete("/{project_id}/api-keys/{key_id}",
               dependencies=[Depends(require_permissions("project:write"))])
async def revoke_api_key(
    project_id: str, key_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    key = await db.get(ProjectAPIKey, key_id)
    if key is None or key.project_id != project_id:
        raise NotFoundError("API Key 不存在")
    key.is_active = False
    await write_audit(
        db, action=AuditAction.API_KEY_REVOKE.value, tenant_id=tenant_id,
        project_id=project_id, resource_type="api_key", resource_id=key_id,
    )
    await db.flush()
    return {"success": True}


# ---------------- Ontology ----------------
@router.get("/{project_id}/ontology", response_model=OntologyOut)
async def get_ontology(
    project_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    onto = await db.scalar(
        select(Ontology).where(
            Ontology.project_id == project_id, Ontology.is_current.is_(True)
        ).order_by(Ontology.version.desc())
    )
    if onto is None:
        raise NotFoundError("本体不存在")
    return OntologyOut(
        id=onto.id, project_id=onto.project_id, name=onto.name,
        description=onto.description,
        entity_types=json.loads(onto.entity_types_json or "[]"),
        edge_types=json.loads(onto.edge_types_json or "[]"),
        version=onto.version, is_current=onto.is_current,
        valid_from=onto.valid_from, valid_until=onto.valid_until,
        created_at=onto.created_at,
    )


@router.put("/{project_id}/ontology", response_model=OntologyOut,
            dependencies=[Depends(require_permissions("project:write"))])
async def upsert_ontology(
    project_id: str, payload: OntologyUpsert,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    # 失效旧版本
    current = await db.scalar(
        select(Ontology).where(
            Ontology.project_id == project_id, Ontology.is_current.is_(True)
        ).order_by(Ontology.version.desc())
    )
    new_version = 1
    if current:
        current.is_current = False
        current.valid_until = utcnow()
        new_version = current.version + 1
    onto = Ontology(
        tenant_id=tenant_id, project_id=project_id, name=payload.name,
        description=payload.description,
        entity_types_json=json.dumps([e.model_dump() for e in payload.entity_types], ensure_ascii=False),
        edge_types_json=json.dumps([e.model_dump() for e in payload.edge_types], ensure_ascii=False),
        is_current=True, version=new_version,
    )
    db.add(onto)
    await db.flush()
    return OntologyOut(
        id=onto.id, project_id=project_id, name=onto.name, description=onto.description,
        entity_types=payload.entity_types, edge_types=payload.edge_types,
        version=onto.version, is_current=True, valid_from=onto.valid_from,
        valid_until=None, created_at=onto.created_at,
    )


# ---------------- 成员 ----------------
@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
async def list_members(
    project_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    rows = (await db.scalars(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    )).all()
    return [ProjectMemberOut.model_validate(m) for m in rows]


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=201,
             dependencies=[Depends(require_permissions("user:manage"))])
async def add_member(
    project_id: str, payload: ProjectMemberCreate,
    current: CurrentUser = Depends(get_current_user),
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    user = await db.get(User, payload.user_id)
    if user is None or user.tenant_id != tenant_id:
        raise NotFoundError("用户不存在或不属于当前租户")
    dup = await db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == payload.user_id
    ))
    if dup:
        raise ConflictError("用户已是项目成员")
    member = ProjectMember(
        project_id=project_id, user_id=payload.user_id,
        project_role=payload.project_role, invited_by=current.id,
    )
    db.add(member)
    await db.flush()
    return ProjectMemberOut.model_validate(member)


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberOut,
              dependencies=[Depends(require_permissions("user:manage"))])
async def update_member(
    project_id: str, member_id: str, payload: ProjectMemberUpdate,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    member = await db.get(ProjectMember, member_id)
    if member is None or member.project_id != project_id:
        raise NotFoundError("成员不存在")
    member.project_role = payload.project_role
    await db.flush()
    return ProjectMemberOut.model_validate(member)


@router.delete("/{project_id}/members/{member_id}",
               dependencies=[Depends(require_permissions("user:manage"))])
async def remove_member(
    project_id: str, member_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_in_tenant(db, project_id, tenant_id)
    member = await db.get(ProjectMember, member_id)
    if member is None or member.project_id != project_id:
        raise NotFoundError("成员不存在")
    await db.delete(member)
    await db.flush()
    return {"success": True}
