"""RBAC 路由：权限列表、角色 CRUD、角色绑定。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_db,
    get_effective_tenant_id,
    require_permissions,
    require_tenant_admin,
)
from core.exceptions import ConflictError, NotFoundError
from core.services.audit_service import write_audit
from models.audit import AuditAction
from models.rbac import Permission, Role, UserRole
from schemas.rbac import (
    PermissionOut,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    UserRoleAssign,
    UserRoleOut,
)

router = APIRouter()


@router.get("/permissions", response_model=list[PermissionOut],
            dependencies=[Depends(require_permissions("user:read"))])
async def list_permissions(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Permission).order_by(Permission.code))).all()
    return [PermissionOut.model_validate(p) for p in rows]


async def _role_out(db: AsyncSession, role: Role) -> RoleOut:
    await db.refresh(role, attribute_names=["permissions"])
    return RoleOut(
        id=role.id, name=role.name, description=role.description,
        is_system=role.is_system, tenant_id=role.tenant_id,
        permissions=[PermissionOut.model_validate(p) for p in role.permissions],
        created_at=role.created_at,
    )


@router.get("/roles", response_model=list[RoleOut],
            dependencies=[Depends(require_permissions("user:read"))])
async def list_roles(
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(
        select(Role).where((Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None)))
    )).all()
    return [await _role_out(db, r) for r in rows]


@router.post("/roles", response_model=RoleOut, status_code=201,
             dependencies=[Depends(require_tenant_admin)])
async def create_role(
    payload: RoleCreate,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    dup = await db.scalar(
        select(Role).where(Role.name == payload.name, Role.tenant_id == tenant_id)
    )
    if dup:
        raise ConflictError("角色名已存在")
    role = Role(name=payload.name, description=payload.description,
                is_system=False, tenant_id=tenant_id)
    if payload.permission_codes:
        perms = (await db.scalars(
            select(Permission).where(Permission.code.in_(payload.permission_codes))
        )).all()
        role.permissions = list(perms)
    db.add(role)
    await db.flush()
    return await _role_out(db, role)


@router.patch("/roles/{role_id}", response_model=RoleOut,
              dependencies=[Depends(require_tenant_admin)])
async def update_role(
    role_id: str, payload: RoleUpdate,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if role is None or (role.tenant_id not in (tenant_id, None)):
        raise NotFoundError("角色不存在")
    if role.is_system:
        raise ConflictError("系统内置角色不可修改")
    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.permission_codes is not None:
        perms = (await db.scalars(
            select(Permission).where(Permission.code.in_(payload.permission_codes))
        )).all()
        role.permissions = list(perms)
    await db.flush()
    return await _role_out(db, role)


@router.delete("/roles/{role_id}", dependencies=[Depends(require_tenant_admin)])
async def delete_role(
    role_id: str,
    tenant_id: str = Depends(get_effective_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if role is None or role.tenant_id != tenant_id:
        raise NotFoundError("角色不存在")
    if role.is_system:
        raise ConflictError("系统内置角色不可删除")
    await db.delete(role)
    await db.flush()
    return {"success": True}


@router.post("/assign", response_model=UserRoleOut, status_code=201,
             dependencies=[Depends(require_tenant_admin)])
async def assign_role(
    payload: UserRoleAssign,
    db: AsyncSession = Depends(get_db),
):
    dup = await db.scalar(select(UserRole).where(
        UserRole.user_id == payload.user_id, UserRole.role_id == payload.role_id,
        UserRole.project_id == payload.project_id,
    ))
    if dup:
        raise ConflictError("已绑定该角色")
    ur = UserRole(user_id=payload.user_id, role_id=payload.role_id,
                  project_id=payload.project_id)
    db.add(ur)
    await write_audit(
        db, action=AuditAction.ROLE_ASSIGN.value, resource_type="user_role",
        resource_id=ur.id, after=payload.model_dump(),
    )
    await db.flush()
    return UserRoleOut.model_validate(ur)


@router.delete("/assign/{user_role_id}", dependencies=[Depends(require_tenant_admin)])
async def revoke_role(user_role_id: str, db: AsyncSession = Depends(get_db)):
    ur = await db.get(UserRole, user_role_id)
    if ur is None:
        raise NotFoundError("绑定不存在")
    await db.delete(ur)
    await db.flush()
    return {"success": True}
