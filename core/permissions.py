"""
RBAC 权限解析
==============
将用户的「系统角色 + 项目成员角色 + 显式角色绑定」解析为权限码集合。

权限来源（并集）：
  1. 系统角色内置权限（SYSTEM_ROLES[system_role]）
  2. 当前项目成员角色内置权限（SYSTEM_ROLES[project_role]）
  3. UserRole 显式绑定的自定义角色权限（租户级 project_id IS NULL，或匹配当前项目）
"""
from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.project import ProjectMember
from models.rbac import (
    Permission,
    Role,
    UserRole,
    role_permission_table,
    SYSTEM_PERMISSIONS,
    SYSTEM_ROLES,
)
from models.user import User, SystemRole

ALL_PERMISSION_CODES: Set[str] = {p[0] for p in SYSTEM_PERMISSIONS}


async def resolve_permissions(
    db: AsyncSession,
    user: User,
    project_id: Optional[str] = None,
) -> Set[str]:
    """解析用户在（可选）指定项目下的全部权限码。"""
    # 超级管理员拥有全部权限
    if user.system_role == SystemRole.SUPER_ADMIN.value:
        return set(ALL_PERMISSION_CODES)

    perms: Set[str] = set()

    # 1. 系统角色内置权限
    perms.update(SYSTEM_ROLES.get(user.system_role, []))

    # 2. 项目成员角色内置权限
    if project_id:
        pm = await db.scalar(
            select(ProjectMember).where(
                ProjectMember.user_id == user.id,
                ProjectMember.project_id == project_id,
            )
        )
        if pm:
            perms.update(SYSTEM_ROLES.get(pm.project_role, []))

    # 3. 显式角色绑定（租户级 + 当前项目级）
    ur_conditions = [UserRole.user_id == user.id]
    stmt = select(UserRole).where(*ur_conditions)
    user_roles = (await db.scalars(stmt)).all()

    role_ids = [
        ur.role_id
        for ur in user_roles
        if ur.project_id is None or ur.project_id == project_id
    ]
    if role_ids:
        code_rows = await db.execute(
            select(Permission.code)
            .join(role_permission_table, role_permission_table.c.permission_id == Permission.id)
            .where(role_permission_table.c.role_id.in_(role_ids))
        )
        perms.update(row[0] for row in code_rows.all())

    return perms


def has_permission(user_permissions: Set[str], required: str) -> bool:
    """支持通配：拥有 'resource:*' 视为该资源全部操作。"""
    if required in user_permissions:
        return True
    resource = required.split(":", 1)[0]
    return f"{resource}:*" in user_permissions or "*" in user_permissions


async def resolve_project_scope(
    db: AsyncSession,
    user: User,
    project,
    fusion: bool = False,
) -> list[str]:
    """
    解析检索/推演的可见项目范围（隔离/融合开关核心）。
      · 隔离（默认 fusion=False）：仅当前项目
      · 融合（fusion=True）：同租户 + 同 fusion_group 的项目集合，
        且**经 RBAC 把关**——非超管/租管仅纳入其有成员资格的项目，防止越权融合。
    """
    from models.project import Project, ProjectMember, ProjectStatus

    if not fusion or not project.fusion_group:
        return [project.id]

    stmt = select(Project.id).where(
        Project.tenant_id == project.tenant_id,
        Project.fusion_group == project.fusion_group,
        Project.status != ProjectStatus.DELETED.value,
    )
    candidate_ids = [r for r in (await db.scalars(stmt)).all()]

    # 超管 / 租管：组内全部可见
    if user.system_role in (SystemRole.SUPER_ADMIN.value, SystemRole.TENANT_ADMIN.value):
        return candidate_ids or [project.id]

    # 普通成员：仅纳入其加入的项目（RBAC 把关）
    member_ids = set(
        (await db.scalars(
            select(ProjectMember.project_id).where(
                ProjectMember.user_id == user.id,
                ProjectMember.project_id.in_(candidate_ids),
            )
        )).all()
    )
    member_ids.add(project.id)  # 当前项目已通过 deps 校验，必在范围内
    return [pid for pid in candidate_ids if pid in member_ids] or [project.id]
